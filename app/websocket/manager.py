"""
WebSocket Connection Manager.

Manages three named channels (doc §6):
  - ws/phone   — Flutter phone app (face)
  - ws/desk    — Flutter desktop app (control room)
  - ws/esp     — ESP32 firmware

Design rule: no device talks to another directly — all messages go through here.
"""

import asyncio
from typing import Dict, Optional, Set

from fastapi import WebSocket

from app.core.logger import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Central hub that holds live WebSocket connections for all channels."""

    def __init__(self):
        # One phone at a time (the robot has one face)
        self._phone: Optional[WebSocket] = None

        # Multiple desktop clients allowed (team monitoring)
        self._desks: Set[WebSocket] = set()

        # One ESP32 at a time
        self._esp: Optional[WebSocket] = None

        self._lock = asyncio.Lock()

    # ── Phone ────────────────────────────────────────────────────────────────

    async def connect_phone(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            if self._phone:
                logger.warning("Phone reconnected — dropping old connection")
                try:
                    await self._phone.close()
                except Exception:
                    pass
            self._phone = ws
        logger.info("📱 Phone connected")

    async def disconnect_phone(self, ws: WebSocket) -> None:
        async with self._lock:
            if self._phone is ws:
                self._phone = None
        logger.info("📱 Phone disconnected")

    async def send_to_phone(self, data: dict | bytes) -> None:
        if self._phone is None:
            return
        try:
            if isinstance(data, bytes):
                await self._phone.send_bytes(data)
            else:
                await self._phone.send_json(data)
        except Exception as e:
            logger.error(f"Error sending to phone: {e}")
            await self.disconnect_phone(self._phone)

    # ── Desktop ───────────────────────────────────────────────────────────────

    async def connect_desk(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._desks.add(ws)
        logger.info(f"🖥️  Desktop connected ({len(self._desks)} active)")

    async def disconnect_desk(self, ws: WebSocket) -> None:
        async with self._lock:
            self._desks.discard(ws)
        logger.info(f"🖥️  Desktop disconnected ({len(self._desks)} remaining)")

    async def broadcast_to_desks(self, data: dict) -> None:
        dead: Set[WebSocket] = set()
        for ws in list(self._desks):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            await self.disconnect_desk(ws)

    # ── ESP32 ─────────────────────────────────────────────────────────────────

    async def connect_esp(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            if self._esp:
                logger.warning("ESP32 reconnected — dropping old connection")
                try:
                    await self._esp.close()
                except Exception:
                    pass
            self._esp = ws
        logger.info("🤖 ESP32 connected")

    async def disconnect_esp(self, ws: WebSocket) -> None:
        async with self._lock:
            if self._esp is ws:
                self._esp = None
        logger.info("🤖 ESP32 disconnected")

    async def send_to_esp(self, data: dict) -> None:
        """Send a command to ESP32. Motion Guard must have already validated it."""
        if self._esp is None:
            logger.warning("ESP32 not connected — command dropped")
            return
        try:
            await self._esp.send_json(data)
        except Exception as e:
            logger.error(f"Error sending to ESP32: {e}")
            await self.disconnect_esp(self._esp)

    # ── Status ───────────────────────────────────────────────────────────────

    @property
    def phone_connected(self) -> bool:
        return self._phone is not None

    @property
    def esp_connected(self) -> bool:
        return self._esp is not None

    @property
    def desk_count(self) -> int:
        return len(self._desks)

    def status(self) -> dict:
        return {
            "phone": self.phone_connected,
            "esp32": self.esp_connected,
            "desktops": self.desk_count,
        }


# Singleton instance shared across the app
manager = ConnectionManager()
