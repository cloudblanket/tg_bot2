_bot = None
_dp = None


def set_bot(bot):
    global _bot
    _bot = bot


def get_bot():
    return _bot


def set_dp(dp):
    global _dp
    _dp = dp


def get_dp():
    return _dp
