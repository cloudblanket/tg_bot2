_bot = None
_dp = None
_bot_username = ""


def set_bot(bot):
    global _bot
    _bot = bot


def get_bot():
    return _bot


def set_bot_username(username: str):
    global _bot_username
    _bot_username = username


def get_bot_username() -> str:
    return _bot_username


def set_dp(dp):
    global _dp
    _dp = dp


def get_dp():
    return _dp
