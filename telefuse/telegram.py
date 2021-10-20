import typing
from pydantic import BaseModel
from . import utils
import json
import pyrogram
from .exceptions import WrongIndexException
from . import abstract
import os
from . import exceptions
import asyncio
import itertools


class TelegramFile(BaseModel):
    name: str
    path: str
    msg_id: int
    filehash: str
    
    @classmethod
    def from_abstract(cls, f: abstract.File, msg_id: int) -> "TelegramFile":
        return cls(
            name = f.name,
            path = f.path,
            msg_id = msg_id,
            filehash = f.get_hash()
        )
    

class FileSystemIndex(BaseModel):
    files: dict[str, TelegramFile]
    index_name: str
    message_id: int = 0
    
    @classmethod
    @utils.retry(3)
    async def _get(cls, client: pyrogram.Client, chat_id: str | int, index_name: str, location: str) -> "FileSystemIndex":
        res = client.search_messages(chat_id=chat_id, query=f"[{index_name}]", limit=1, filter="document")
        try:
            res = await res.__anext__()
        except StopAsyncIteration:
            raise WrongIndexException(f"Can not find index with name {index_name}")

        await client.download_media(res, location)
        
        with open(location, 'r') as f:
            msg = json.load(f)
        try:
            return cls(**msg)
        except Exception:
            raise WrongIndexException("Index is corrupted")
    
    @utils.retry(3)
    async def save(self, client: pyrogram.Client, chat_id: str | int, location: str):
        with open(location, 'w') as f:
            f.write(self.json())
        if self.message_id == 0:
            msg = await client.send_document(chat_id=chat_id, document=location, caption=f"[{self.index_name}]")
            if msg is None:
                raise exceptions.RetryableError("Cannot save index")
            self.message_id = msg.message_id
            with open(location, 'w') as f:
                f.write(self.json())
        await client.edit_message_media(chat_id=chat_id, message_id=self.message_id, media=pyrogram.types.InputMediaDocument(
                    media=location,
                    caption=f"[{self.index_name}]"
                )
            )


class OperationCtx:
    def __init__(self, fs: "TelegramFileSystem", max_inflight: int) -> None:
        self._semaphore = asyncio.Semaphore(max_inflight)
        self._files_to_get: list[abstract.File] = []
        self._files_to_add: list[abstract.File] = []
        self._files_to_delete: list[abstract.File] = []
        self._fs = fs
        
    async def __aenter__(self):
        self._files_to_get = []
        self._files_to_add = []
        self._files_to_delete = []
        return self
    
    def add(self, f: abstract.File):
        self._files_to_add.append(f)
    
    def get(self, f: abstract.File):
        self._files_to_get.append(f)
    
    def delete(self, f: abstract.File):
        self._files_to_delete.append(f)
    
    async def __upload(self, file: abstract.File):
        async with self._semaphore:
            await self._fs.init_file(file, with_save=False)
    
    async def __get(self, file: abstract.File):
        async with self._semaphore:
            await self._fs.get_file(file)

    async def __delete(self, file: abstract.File):
        async with self._semaphore:
            await self._fs.remove_file(file, with_save=False)
    
    async def save(self):
        add = {file.path: file for file in self._files_to_add}
        delete = {file.path: file for file in self._files_to_delete}
        get = {file.path: file for file in self._files_to_get}
        
        for key in add:
            get.pop(key, None)
        for key in delete:
            add.pop(key, None)
            get.pop(key, None)
        
        tasks = [self.__upload(file) for file in add.values()]
        tasks.extend(self.__get(file) for file in get.values())
        tasks.extend(self.__delete(file) for file in delete.values())
        await asyncio.gather(*tasks)
        await self._fs.save()
    
    async def __aexit__(self, exception_type, exception_value, exception_traceback):
        if exception_type is None:
            await self.save()
            self._files_to_get = []
            self._files_to_add = []
            self._files_to_delete = []


class TelegramFileSystem:
    
    def __init__(self, api: "TelegramApi", index: FileSystemIndex, chat_id: str | int, client: pyrogram.Client, location: str) -> None:
        self._api = api
        self._index = index
        self._chat_id = chat_id
        self._client = client
        self._location = location
    
    @property
    def files(self) -> typing.Iterable[str]:
        return iter(self._index.files)
    
    def get_file_from_local_index(self, file_path: str) -> TelegramFile | None:
        return self._index.files.get(file_path)
    
    @classmethod
    async def with_telegram_api(cls, api: "TelegramApi", client: pyrogram.Client, chat_id: str | int, index_name: str, location: str) -> "TelegramFileSystem":
        index = await FileSystemIndex._get(client=client, chat_id=chat_id, index_name=index_name, location=location)
        return cls(api, index, chat_id, client, location)
    
    async def init_file(self, file: abstract.File, with_save: bool = True) -> None:
        msg_id = None if not self._index.files.get(file.path) else self._index.files[file.path].msg_id
        curr_msg_id = await self._api.upload_file(self._chat_id, file, msg_id=msg_id, progres=file.progress)
        self._index.files[file.path] = TelegramFile.from_abstract(file, curr_msg_id)
        if with_save:
            await self._index.save(self._client, self._chat_id, self._location)
    
    async def get_file(self, file: abstract.File):
        f = self._index.files.get(file.path)
        if f is None:
            raise exceptions.FileNotFound(f"No file {file.path} in index")
        await self._api.download_file(chat_id=self._chat_id, file_path=file.real_path, msg_id=f.msg_id, progres=file.progress)
    
    async def remove_file(self, file: abstract.File, with_save: bool = True) -> None:
        f = self._index.files.get(file.path)
        if f is None:
            raise exceptions.FileNotFound(f"No file {file.path} in index")
        await self._api.delete_msg(self._chat_id, f.msg_id)
        self._index.files.pop(file.path)
        if with_save:
            await self._index.save(self._client, self._chat_id, self._location)
    
    async def save(self):
        await self._index.save(self._client, self._chat_id, self._location)
    
    def clone(self) -> "TelegramFileSystem":
        return TelegramFileSystem(self._api, self._index.copy(), self._chat_id, self._client, self._location)
    
    def operation(self, max_inflight: int = 15) -> OperationCtx:
        return OperationCtx(self.clone(), max_inflight)


class TelegramApi:
    def __init__(self, client: pyrogram.Client) -> None:
        self._client = client
        
    @utils.retry(3)
    async def upload_file(self, chat_id: str | int, file: abstract.File, msg_id: int | None = None, progres=lambda x, y: None) -> int:
        if file.get_size() == 0:
            return 0
        
        if msg_id == 0:
            msg_id = None
        
        if msg_id is not None:
            msg = await self._client.edit_message_media(
                chat_id=chat_id,
                message_id=msg_id,
                file_name=file.name,
                media=pyrogram.types.InputMediaDocument(
                    media=file.real_path,
                )
            )
            return msg.message_id
        msg = await self._client.send_document(
            chat_id=chat_id,
            document=file.real_path,
            file_name=file.name,
            force_document=True,
            progress=progres
        )
        if msg is None:
            raise exceptions.RetryableError(f"Cannot upload file {file.name}")
        return msg.message_id
    
    @utils.retry(3)
    async def download_file(self, chat_id: str | int, file_path: str, msg_id: int, progres=lambda x, y: None):
        if msg_id == 0:
            if not os.path.exists(file_path):
                open(file_path, 'x').close()
            return
        msg = await self._client.get_messages(chat_id=chat_id, message_ids=msg_id)
        await self._client.download_media(
            msg,
            file_name=file_path,
            progress=progres
        )
    
    @utils.retry(3)
    async def delete_msg(self, chat_id: str | int, msg_id: int) -> None:
        if msg_id == 0:
            return
        await self._client.delete_messages(chat_id=chat_id, message_ids=msg_id)