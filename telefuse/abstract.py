import abc


class File(abc.ABC):
    name: str
    path: str
    real_path: str
