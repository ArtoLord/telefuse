import functools
import typing
from pyrogram.errors import RPCError
import time
from . import exceptions

def retry(max_num: int, allowed_errors: list[typing.Type[Exception]] = None, sleep_time:float = 1):
    if allowed_errors is None:
        allowed_errors = [RPCError, exceptions.RetryableError]
    def decorator(f: typing.Callable[..., typing.Awaitable]):
        @functools.wraps(f)
        async def wrapper(*args, **kwargs):
            for i in range(max_num):
                try:
                    return await f(*args, **kwargs)
                except Exception as e:
                    if type(e) not in allowed_errors:
                        raise e
                    if i == max_num - 1:
                        raise e
                    time.sleep(sleep_time)
        return wrapper
    return decorator