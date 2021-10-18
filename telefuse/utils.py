import functools
import typing
from pyrogram.errors import RPCError
import time
from . import exceptions


# Print iterations progress
def printProgressBar (iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█', printEnd = "\r"):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end = printEnd)
    # Print New Line on Complete
    if iteration == total: 
        print()


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