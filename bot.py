from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config import (
    TELEGRAM_TOKEN, DEEPSEEK_API_KEY, ADMIN_IDS, MODEL, MODEL_REASONING,
    GEMINI_API_KEY, WEBHOOK_DOMAIN, WEBHOOK_URL, WEBHOOK_PORT, WEBHOOK_PATH,
    CACHE_TTL_HOURS, SUMMARY_THRESHOLD, SUMMARY_KEEP, RATE_MAX_PER_WINDOW,
    RATE_WINDOW_SEC, REDIS_HOST, REDIS_PORT,
)
from core.runtime import tavily_available, cloudinary_ready, db, redis_client
from handlers.command_handler import (
    start, help_cmd, hapus, status_cmd, storage_cmd, file_txt_cmd, file_zip_cmd,
    cek_pending_cmd, cancel_pending_cmd, clearfile_cmd, export_docx_cmd,
    retry_cmd, mode_cmd, mode_callback, log_cmd, users_cmd, backend_cmd, memory_cmd, rules_cmd,
)
from handlers.exec_handler import exec_cmd, srv_status_cmd
from handlers.admin_handler import admin_stats, admin_list_users, admin_clear_user, admin_cache_clear
from handlers.message_handler import chat
from handlers.lifecycle import scheduled_cleanup, post_init, error_handler


def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError('TELEGRAM_TOKEN belum diset.')
    if not DEEPSEEK_API_KEY:
        raise RuntimeError('DEEPSEEK_API_KEY belum diset.')

    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler('start',      start))
    app.add_handler(CommandHandler('help',       help_cmd))
    app.add_handler(CommandHandler('hapus',      hapus))
    app.add_handler(CommandHandler('status',     status_cmd))
    app.add_handler(CommandHandler('storage',    storage_cmd))
   # app.add_handler(CommandHandler('file_txt',   file_txt_cmd))
    #app.add_handler(CommandHandler('file_zip',   file_zip_cmd))
    app.add_handler(CommandHandler('cek',        cek_pending_cmd))
    app.add_handler(CommandHandler('cancel',     cancel_pending_cmd))
    app.add_handler(CommandHandler('clearfile',  clearfile_cmd))
    app.add_handler(CommandHandler('exportdocx', export_docx_cmd))
    app.add_handler(CommandHandler('log', log_cmd))
    app.add_handler(CommandHandler("backend", backend_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("memory", memory_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))

    app.add_handler(CommandHandler('exec', exec_cmd))
    for _typo in ['exex', 'exce', 'ecec', 'eexc', 'excec']:
        app.add_handler(CommandHandler(
            _typo,
            lambda u, c: u.message.reply_text(
                '⌨️ Typo? Maksudnya `/exec`?\n\nContoh: `/exec ping 1.1.1.1`',
                parse_mode=ParseMode.MARKDOWN,
            ) if u.message else None,
        ))
    app.add_handler(CommandHandler('srv', srv_status_cmd))

    app.add_handler(CommandHandler('retry', retry_cmd))
    app.add_handler(CommandHandler('mode',  mode_cmd))
    app.add_handler(CallbackQueryHandler(mode_callback, pattern='^mode_'))

    app.add_handler(CommandHandler('stats',       admin_stats))
    app.add_handler(CommandHandler('listusers',   admin_list_users))
    app.add_handler(CommandHandler('clear_user',  admin_clear_user))
    app.add_handler(CommandHandler('cache_clear', admin_cache_clear))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, chat))

    app.add_error_handler(error_handler)
    app.job_queue.run_repeating(scheduled_cleanup, interval=300, first=60)

    print('=' * 60)
    print('🤖 Bot starting...')
    print(f'👑 Admin IDs      : {ADMIN_IDS}')
    print(f'🤖 Model Chat     : {MODEL}')
    print(f'🧠 Model Reasoning: {MODEL_REASONING}')
    print(f'🔑 Gemini Vision  : {"✅" if GEMINI_API_KEY else "❌"}')
    print(f'🔍 Web Search     : {"✅ Tavily" if tavily_available else "⚠ DeepSeek fallback"}')
    print(f'☁️  Cloudinary     : {"✅" if cloudinary_ready else "❌"}')
    print(f'📁 Firestore      : {"✅ Connected" if db else "⚠ Local only"}')
    print('⚙️  Exec           : Lokal (subprocess)')
    print(f'⚡ Answer Cache   : {"✅ Firebase" if db else "❌"} (TTL {CACHE_TTL_HOURS // 24}d)')
    print(f'🧠 Auto Summarize : tiap {SUMMARY_THRESHOLD} pesan (keep {SUMMARY_KEEP})')
    print(f'🔒 Rate Limit     : {RATE_MAX_PER_WINDOW} req/{RATE_WINDOW_SEC//60}min per user')
    if redis_client:
        print(f'🔴 Redis          : {REDIS_HOST}:{REDIS_PORT} (connected)')
    else:
        print('⚠ Redis          : tidak tersedia — pakai RAM')
    print(f'🌐 Mode           : {"Webhook" if WEBHOOK_DOMAIN else "Polling"}')
    if WEBHOOK_DOMAIN:
        print(f'🔗 Webhook URL    : {WEBHOOK_URL}')
        print(f'🔌 Listen port    : {WEBHOOK_PORT}')
    print('=' * 60)

    if WEBHOOK_DOMAIN:
        print(f'🔗 Webhook mode: {WEBHOOK_URL}')
        print(f'⚠️  Pastikan port {WEBHOOK_PORT} terbuka dan SSL valid di {WEBHOOK_DOMAIN}')
        app.run_webhook(
            listen='0.0.0.0',
            port=WEBHOOK_PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=WEBHOOK_URL,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        print('🔄 Polling mode — tidak butuh webhook/SSL')
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )


if __name__ == '__main__':
    main()