"""Telegram control bot.

Runs inside the miner's own asyncio loop (python-telegram-bot v21+ is async).
Owner = ``chat_id``; guests = ``allowed_users`` (read-only commands only).

Commands
    /start /help /status /balance /accounts   everyone allowed
    /restart                                   owner only
    /language <en|de>                          owner only
"""

from __future__ import annotations

from loguru import logger

from ..i18n import available_languages, load_language, t
from .base import summarize_accounts

try:
    from telegram import Update
    from telegram.constants import ParseMode
    from telegram.ext import Application, CommandHandler, ContextTypes

    _PTB = True
except ImportError:  # pragma: no cover - optional dependency
    _PTB = False


class TelegramBot:
    def __init__(self, cfg, *, request_restart=None) -> None:
        self.cfg = cfg
        self.enabled = bool(cfg.enabled and cfg.bot_token) and _PTB
        self._request_restart = request_restart
        self._manager = None
        self._app = None

        if cfg.enabled and not _PTB:
            logger.warning(
                "Telegram enabled but python-telegram-bot is not installed."
            )

    def bind(self, manager) -> None:
        self._manager = manager

    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        if not self.enabled:
            return
        self._app = Application.builder().token(self.cfg.bot_token).build()
        for name, handler in (
            ("start", self._cmd_help),
            ("help", self._cmd_help),
            ("status", self._cmd_status),
            ("balance", self._cmd_balance),
            ("accounts", self._cmd_accounts),
            ("restart", self._cmd_restart),
            ("language", self._cmd_language),
        ):
            self._app.add_handler(CommandHandler(name, handler))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot polling.")

    async def stop(self) -> None:
        if self._app is None:
            return
        try:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Telegram shutdown: {exc}")
        finally:
            self._app = None

    # ------------------------------------------------------------------ #
    # push notifications (best-effort, owner + guests)

    async def _broadcast(self, text: str) -> None:
        if self._app is None:
            return
        recipients = {str(self.cfg.chat_id)} | {str(u) for u in self.cfg.allowed_users}
        for chat in filter(None, recipients):
            try:
                await self._app.bot.send_message(chat_id=chat, text=text)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Telegram send to {chat}: {exc}")

    async def notify_points(self, alias: str, snap: dict, old: int, new: int) -> None:
        name = snap.get("name") if isinstance(snap, dict) else snap
        await self._broadcast(
            f"💰 {alias} · {name}: +{new - old} (total {new:,})"
        )

    async def notify_status(self, alias: str, snap: dict, action: str) -> None:
        name = snap.get("name") if isinstance(snap, dict) else snap
        await self._broadcast(f"📡 {alias} · {name}: {action}")

    # ------------------------------------------------------------------ #

    def _is_owner(self, uid: int) -> bool:
        return str(uid) == str(self.cfg.chat_id)

    def _is_allowed(self, uid: int) -> bool:
        return self._is_owner(uid) or uid in self.cfg.allowed_users

    async def _guard(self, update: "Update", owner_only: bool) -> bool:
        uid = update.effective_user.id if update.effective_user else 0

        # First contact with no owner configured -> claim this user as owner
        # (session only; tell them to persist it in config.json).
        if not str(self.cfg.chat_id).strip() and uid:
            self.cfg.chat_id = str(uid)
            logger.warning(
                f"Telegram: no owner configured - claiming user {uid} as owner "
                f"for this session. Put \"chat_id\": \"{uid}\" in config.json to keep it."
            )
            await update.message.reply_text(
                f"You are now the owner for this session (id {uid}).\n"
                f'Add  "chat_id": "{uid}"  to config.json → Telegram to make it permanent.'
            )

        ok = self._is_owner(uid) if owner_only else self._is_allowed(uid)
        if not ok:
            await update.message.reply_text(t("tg_denied"))
        return ok

    async def _cmd_help(self, update, _ctx) -> None:
        if not await self._guard(update, owner_only=False):
            return
        await update.message.reply_text(t("tg_help"))

    async def _cmd_status(self, update, _ctx) -> None:
        if not await self._guard(update, owner_only=False):
            return
        await self._send_overview(update)

    async def _cmd_accounts(self, update, _ctx) -> None:
        if not await self._guard(update, owner_only=False):
            return
        await self._send_overview(update)

    async def _cmd_balance(self, update, _ctx) -> None:
        if not await self._guard(update, owner_only=False):
            return
        await self._send_overview(update)

    async def _send_overview(self, update) -> None:
        if self._manager is None:
            await update.message.reply_text(t("tg_not_ready"))
            return
        text = summarize_accounts(self._manager.snapshot())
        await update.message.reply_text(f"```\n{text}\n```", parse_mode=ParseMode.MARKDOWN)

    async def _cmd_restart(self, update, _ctx) -> None:
        if not await self._guard(update, owner_only=True):
            return
        await update.message.reply_text(t("tg_restarting"))
        if self._request_restart is not None:
            self._request_restart()

    async def _cmd_language(self, update, ctx) -> None:
        if not await self._guard(update, owner_only=True):
            return
        args = ctx.args or []
        if not args or args[0].lower() not in available_languages():
            await update.message.reply_text(
                t("tg_language_usage", available=", ".join(available_languages()))
            )
            return
        active = load_language(args[0].lower())
        await update.message.reply_text(t("language_set", lang=active))
