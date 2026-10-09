"""twin/ -- the balance demo app on the bot/ vehicle stack.

The whole chain (MuJoCo physics, the mailbox word contract, the
Controller slot + BalanceController, the Renode channel, the ws server)
lives in bot/. This package keeps only the application: TwinLoop's
mode/drive_duty defaults + set_mode, the drive stub + make_backend
factory, the TWN2 mailbox layout, the fwconfig generator, the Renode
backend, and the CLI: python -m twin --balance --serve
"""
