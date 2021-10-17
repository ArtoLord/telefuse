from fs.osfs import OSFS
import pydantic
import os
import json


FS_FILE_NAME = ".telefs"


class FsNotFoundException(Exception):
    pass


class FsConfig(pydantic.BaseModel):
    chat_id: str
    session: str
    index_name: str
    dir_path: str
    
    @classmethod
    def find(cls, curr_path: str) -> "FsConfig":
        with OSFS("/") as fs:
            while curr_path:
                print(curr_path)
                for file in fs.listdir(curr_path):
                    if file == FS_FILE_NAME:
                        try:
                            with fs.open(os.path.join(curr_path, FS_FILE_NAME), "r") as f:
                                return cls(**json.load(f))
                        except Exception:
                            pass
                if curr_path == "/":
                    raise FsNotFoundException
                curr_path = os.path.abspath(os.path.join(curr_path, os.path.pardir))
    
    def get_path(self, path: str) -> str:
        return os.path.relpath(path, start=self.dir_path)