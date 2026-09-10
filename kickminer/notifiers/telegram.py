"""Telegram control bot.

Runs inside the miner's own asyncio loop (python-telegram-bot v21+ is async).
Single user: ``chat_id`` is the only account that may use it. If ``chat_id``
is empty the first person to message the bot claims it for the session.

Commands: /start /help /status /balance /accounts /restart /language <en|de>
"""

from __future__ import annotations

from loguru import logger

from ..i18n import available_languages, load_language, t
from .base import (
    EMOJI,
    account_label,
    msg_error,
    msg_no_points,
    msg_points,
    msg_status,
    msg_token_expired,
    summarize_accounts,
)

try:
    from telegram import Update
    from telegram.constants import ParseMode
    from telegram.error import Conflict
    from telegram.ext import Application, CommandHandler, ContextTypes

    _PTB = True
except ImportError:  # pragma: no cover - optional dependency
    _PTB = False
    Conflict = Exception


def _polling_error(exc: Exception) -> None:
    if isinstance(exc, Conflict):
        logger.warning(
            "Telegram: another instance is polling this bot token "
            "(is the miner running twice?). Retrying."
        )
    else:
        logger.debug(f"Telegram polling error: {exc}")


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
        await self._app.updater.start_polling(
            drop_pending_updates=True, error_callback=_polling_error
        )
        logger.info("Telegram bot polling.")

        if getattr(self.cfg, "notify_startup", True) and str(self.cfg.chat_id).strip():
            try:
                await self._app.bot.send_message(
                    chat_id=self.cfg.chat_id,
                    text=f"{EMOJI['start']} Kick Miner is online.",
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Telegram startup ping failed: {exc}")

    def _on(self, flag: str) -> bool:
        return self.enabled and bool(getattr(self.cfg, flag, True))

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
    # push notifications to the single owner (best-effort)

    async def _broadcast(self, text: str) -> None:
        chat = str(self.cfg.chat_id).strip()
        if self._app is None or not chat:
            return
        try:
            await self._app.bot.send_message(chat_id=chat, text=text)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Telegram send to {chat}: {exc}")

    # message text comes from notifiers.base so Discord and Telegram stay identical
    _acct = staticmethod(account_label)

    async def notify_points(self, alias: str, snap: dict, old: int, new: int) -> None:
        if not self._on("notify_points"):
            return
        if new - old < max(1, getattr(self.cfg, "min_points_gain", 1)):
            return
        await self._broadcast(msg_points(alias, snap, old, new))

    async def notify_status(self, alias: str, snap: dict, action: str) -> None:
        if self._on("notify_status_change"):
            await self._broadcast(msg_status(alias, snap, action))

    async def notify_no_points(self, alias: str, snap: dict) -> None:
        if self._on("notify_errors"):
            await self._broadcast(msg_no_points(alias, snap))

    async def notify_error(self, alias: str, streamer: str, message: str) -> None:
        if self._on("notify_errors"):
            await self._broadcast(msg_error(alias, streamer, message))

    async def notify_token_expired(self, alias: str) -> None:
        if self._on("notify_errors"):
            await self._broadcast(msg_token_expired(alias))

    # ------------------------------------------------------------------ #

    def _is_owner(self, uid: int) -> bool:
        return str(uid) == str(self.cfg.chat_id)

    async def _guard(self, update: "Update") -> bool:
        uid = update.effective_user.id if update.effective_user else 0

        # First contact with no owner configured -> claim this user as owner
        # (session only; tell them to persist it in config.json).
        if not str(self.cfg.chat_id).strip() and uid:
            self.cfg.chat_id = str(uid)
            logger.warning(
                f"Telegram: no owner configured - claiming user {uid} as owner "
                f"for this session. Set it in the dashboard Notifications tab to keep it."
            )
            await update.message.reply_text(
                f"You are now the owner for this session (id {uid}).\n"
                "Enter this id in the dashboard Notifications tab to make it permanent."
            )

        if not self._is_owner(uid):
            await update.message.reply_text(t("tg_denied"))
            return False
        return True

    async def _cmd_help(self, update, _ctx) -> None:
        if not await self._guard(update):
            return
        await update.message.reply_text(t("tg_help"))

    async def _cmd_status(self, update, _ctx) -> None:
        if not await self._guard(update):
            return
        await self._send_overview(update)

    async def _cmd_accounts(self, update, _ctx) -> None:
        if not await self._guard(update):
            return
        await self._send_overview(update)

    async def _cmd_balance(self, update, _ctx) -> None:
        if not await self._guard(update):
            return
        await self._send_overview(update)

    async def _send_overview(self, update) -> None:
        if self._manager is None:
            await update.message.reply_text(t("tg_not_ready"))
            return
        text = summarize_accounts(self._manager.snapshot())
        await update.message.reply_text(f"```\n{text}\n```", parse_mode=ParseMode.MARKDOWN)

    async def _cmd_restart(self, update, _ctx) -> None:
        if not await self._guard(update):
            return
        await update.message.reply_text(t("tg_restarting"))
        if self._request_restart is not None:
            self._request_restart()

    async def _cmd_language(self, update, ctx) -> None:
        if not await self._guard(update):
            return
        args = ctx.args or []
        if not args or args[0].lower() not in available_languages():
            await update.message.reply_text(
                t("tg_language_usage", available=", ".join(available_languages()))
            )
            return
        active = load_language(args[0].lower())
        await update.message.reply_text(t("language_set", lang=active))
