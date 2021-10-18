class WrongIndexException(Exception):
    pass


class RetryableError(Exception):
    pass


class FileNotFound(Exception):
    pass


class CommandValidationError(Exception):
    pass