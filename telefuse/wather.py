from . import telegram
from . import config
from . import abstract
import asyncio
from asyncinotify import Inotify, Mask
import typing

class Wather:
    def __init__(self, fs: telegram.TelegramFileSystem, file_factory: typing.Callable[[str], abstract.File], period_time: float = 20) -> None:
        self.operation: telegram.OperationCtx = fs.operation()
        self.fs = fs
        self.file_factory = file_factory
        self.lock = asyncio.Lock()
        self.stop_event = asyncio.Event()
        self.period_time = period_time
        self.wather: asyncio.Task | None = None
        self.main: asyncio.Task | None = None
    
    async def wather_coro(self, main_dir: str, fs_config: config.FsConfig):
        files = set(self.fs.files)
        with Inotify() as inotify:
            inotify.add_watch(main_dir, Mask.MODIFY | Mask.DELETE)
            async for event in inotify:
                if event.path is None:
                    continue
                if fs_config.get_path(event.path.absolute().as_posix()) not in files:
                    continue
                async with self.lock:
                    print(event)
                    match event.mask:
                        case Mask.MODIFY:
                            self.operation.add(self.file_factory(event.path.absolute().as_posix()))
                        case Mask.DELETE:
                            self.operation.delete(self.file_factory(event.path.absolute().as_posix()))
    
    async def main_coro(self):
        while True:
            async with self.lock:
                print("Uploading")
                await self.operation.save()
            try:
                await asyncio.wait_for(self.stop_event.wait(), self.period_time)
                async with self.lock:   
                    print("Uploading")
                    await self.operation.save()
                break
            except asyncio.TimeoutError:
                continue
    
    async def stop(self):
        self.stop_event.set()
        if self.main is not None:
            await self.main
        if self.wather is not None:
            try:
                self.wather.cancel()
            except asyncio.CancelledError:
                pass
            await self.wather
        
    
    async def start_and_wait(self, main_dir: str, fs_config: config.FsConfig):
        wather = asyncio.create_task(self.wather_coro(main_dir, fs_config))
        self.wather = wather
        self.main = asyncio.create_task(self.main_coro())
        await self.main
        