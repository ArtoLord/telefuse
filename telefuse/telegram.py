import typing
from pydantic import BaseModel
import utils
import json
import pyrogram
from exceptions import WrongIndexException
import abstract
import io
import exceptions
import asyncio

class FileSystemIndex(BaseModel):
    files: dict[str, int]
    index_name: str
    message_id: int = 0
    
    @classmethod
    @utils.retry(3)
    async def _get(cls, client: pyrogram.Client, chat_id: str | int, index_name: str) -> "FileSystemIndex":
        async with client:
            res = client.search_messages(chat_id=chat_id, query=f"[{index_name}]", limit=1)
            try:
                res = await res.__anext__()
            except StopAsyncIteration:
                raise WrongIndexException(f"Can not find index with name {index_name}")
            msg = res.text
            msg = ''.join(msg.split('\n')[1:])
            try:
                return cls(**json.loads(msg))
            except Exception:
                raise WrongIndexException("Index is corrupted")
    
    @utils.retry(3)
    async def save(self, client: pyrogram.Client, chat_id: str | int):
        async with client:
            if self.message_id == 0:
                msg = await client.send_message(chat_id=chat_id, text=f"[{self.index_name}]\n{self.json()}")
                self.message_id = msg.message_id
            await client.edit_message_text(chat_id=chat_id, text=f"[{self.index_name}]\n{self.json()}", message_id=self.message_id)

class TelegramFileSystem:
    
    def __init__(self, api: "TelegramApi", index: FileSystemIndex, chat_id: str | int, client: pyrogram.Client) -> None:
        self._api = api
        self._index = index
        self._chat_id = chat_id
        self._client = client
    
    @classmethod
    async def with_telegram_api(cls, api: "TelegramApi", client: pyrogram.Client, chat_id: str | int, index_name: str) -> "TelegramFileSystem":
        index = await FileSystemIndex._get(client=client, chat_id=chat_id, index_name=index_name)
        return cls(api, index, chat_id, client)
    
    async def init_file(self, file: abstract.File) -> None:
        msg_id = self._index.files.get(file.path)
        msg_id = await self._api.upload_file(self._chat_id, file, msg_id=msg_id)
        self._index.files[file.path] = msg_id
        await self._index.save(self._client, self._chat_id)
    
    async def get_file(self, file: abstract.File):
        msg_id = self._index.files.get(file.path)
        if msg_id is None:
            raise exceptions.FileNotFound(f"No file {file.path} in index")
        await self._api.download_file(chat_id=self._chat_id, file_path=file.real_path, msg_id=msg_id)
    
    async def remove_file(self, file: abstract.File) -> None:
        msg_id = self._index.files.get(file.path)
        if msg_id is None:
            raise exceptions.FileNotFound(f"No file {file.path} in index")
        msg_id = await self._api.delete_msg(self._chat_id, msg_id)
        self._index.files.pop(file.path)
        await self._index.save(self._client, self._chat_id)
    
    async def save(self):
        await self._index.save(self._client, self._chat_id)


class TelegramApi:
    def __init__(self, client: pyrogram.Client) -> None:
        self._client = client

    @utils.retry(3)
    async def upload_empty_file(self, chat_id: str | int, file: abstract.File) -> int:
        msg = await self._client.send_document(
                chat_id=chat_id,
                document=io.BytesIO(b""),
                file_name=file.name,
                force_document=True
            )
        if msg is None:
                raise exceptions.RetryableError(f"Cannot upload file {file.name}")
        return msg.message_id
        
    @utils.retry(3)
    async def upload_file(self, chat_id: str | int, file: abstract.File, msg_id: int = None) -> int:
        async with self._client:
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
                force_document=True
            )
            if msg is None:
                raise exceptions.RetryableError(f"Cannot upload file {file.name}")
            return msg.message_id
    
    @utils.retry(3)
    async def download_file(self, chat_id: str | int, file_path: str, msg_id: int):
        async with self._client:
            msg = await self._client.get_messages(chat_id=chat_id, message_ids=msg_id)
            await self._client.download_media(
                msg,
                file_name=file_path
            )
    
    @utils.retry(3)
    async def delete_msg(self, chat_id: str | int, msg_id: int) -> None:
        async with self._client:
            await self._client.delete_messages(chat_id=chat_id, message_ids=msg_id)