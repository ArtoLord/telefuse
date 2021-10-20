import abc


class File(abc.ABC):
    name: str
    path: str
    real_path: str
    
    @abc.abstractmethod
    def progress(self, curr: int, total: int):
        pass
    
    @abc.abstractmethod
    def get_hash(self) -> str:
        pass