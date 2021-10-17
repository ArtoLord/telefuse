import abc


class File(abc.ABC):
    name: str
    path: str
    real_path: str
    
    @abc.abstractclassmethod
    async def form_path(cls, path: str) -> "File":
        pass
