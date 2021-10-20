import abc
import argparse
from . import config
import typing
from . import telegram
import pyrogram
from . import exceptions
from . import abstract
import os
import json
from . import config
from . import utils


class ProgressBar:
    def __init__(self, length: int = 10, decimal: int = 10, name: str = "uploading"):
        self.files: dict[str, tuple[int, int]] = {}
        self.sum: int = 0
        self.total_sum: int = 0
        self.length: int = length
        self.decimal: int = decimal
        self.name = name
    
    def print(self, filename: str, curr: int, total: int):
        self.total_sum -= self.files.get(filename, (0, 0))[1]
        self.sum -= self.files.get(filename, (0, 0))[0]
        self.total_sum += total
        self.sum += curr
        self.files[filename] = (curr, total)
        utils.printProgressBar(
            iteration=self.sum,
            total=self.total_sum,
            suffix=f"{self.name} {filename} {self.sum}/{self.total_sum}",
            length=self.length,
            decimals=self.decimal,
        )


class File(abstract.File):
    def __init__(self, path: str, real_path: str, progress_bar: ProgressBar) -> None:
        self.path = path
        self.name = os.path.basename(path)
        self.real_path = real_path
        self.progress_bar = progress_bar
    
    def progress(self, curr: int, total: int):
        self.progress_bar.print(self.path, curr, total)
    
    def get_hash(self) -> str:
        return utils.hash_file(self.real_path)


class Command(abc.ABC):
    
    def __init__(self, client: pyrogram.Client, parser: argparse._SubParsersAction, app_config: config.AppConfig, fs_config: config.FsConfig | None) -> None:
        async def exec(args: argparse.Namespace):
            async with client:
                return await self.run(client, args, app_config, fs_config)
        pars = self.edit_argparser(parser)
        pars.set_defaults(func=exec)
    
    @classmethod
    @abc.abstractclassmethod
    def edit_argparser(cls, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        raise NotImplemented
    
    @classmethod
    @abc.abstractclassmethod
    async def run(cls, client: pyrogram.Client, args: argparse.Namespace, app_config: config.AppConfig, fs_config: config.FsConfig | None):
        pass


def init_commands(client: pyrogram.Client, parser: argparse._SubParsersAction, app_config: config.AppConfig, fs_config: config.FsConfig | None) -> list[Command]:
    
    commands: list[typing.Type[Command]] = [
        Get,
        Add,
        Rm,
        Init,
        Clone,
        Status,
        Download,
        Upload
    ]
    
    return [
        command(client, parser, app_config, fs_config) for command in commands
    ]


class FileCommand(Command, abc.ABC):
    command_name: str | None = None
    command_help: str | None = None
    must_exist: bool = True
    expect_dirs: bool = False
    
    @classmethod
    def edit_argparser(cls, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        if cls.command_name is None or cls.command_help is None:
            raise NotImplemented
        arg = parser.add_parser(cls.command_name, description=cls.command_help)
        arg.add_argument("files", help=f"Path of file for {cls.command_name}", nargs="+")
        return arg
    
    @classmethod
    @abc.abstractclassmethod
    async def exec(cls, client: pyrogram.Client, file_path:str, app_config: config.AppConfig, fs_config: config.FsConfig, operation: telegram.OperationCtx, pb: ProgressBar):
        pass
    
    @classmethod
    async def run(cls, client: pyrogram.Client, args: argparse.Namespace, app_config: config.AppConfig, fs_config: config.FsConfig | None):
        if fs_config is None:
            raise exceptions.WrongIndexException("Index not found, but must be specified. Run init command to create new index")
        fs = await telegram.TelegramFileSystem.with_telegram_api(
            telegram.TelegramApi(client),
            client,
            fs_config.chat_id,
            fs_config.index_name
        )
        
        progress_bar = ProgressBar()
        
        files = {os.path.abspath(file) for file in args.files}
        if cls.expect_dirs:
            for file_path in files.copy():
                if os.path.exists(file_path) and os.path.isdir(file_path):
                    files.remove(file_path)
                    for dirpath, dirnames, filenames in os.walk(file_path):
                        files = files | {
                            os.path.join(file_path, dirpath, filename)
                            for filename in filenames
                        }
        async with fs.operation() as op:
            for file_path in files:
                if cls.must_exist and not os.path.exists(file_path):
                    raise exceptions.CommandValidationError(f"File {file_path} is not walid")
                await cls.exec(
                    client, file_path, app_config, fs_config, op, progress_bar
                )
    
    
class Add(FileCommand):
    command_name = "add"
    command_help = "Add file to index and upload it to telegram"
    expect_dirs = True
    
    @classmethod
    async def exec(cls, client: pyrogram.Client, file_path: str, app_config: config.AppConfig, fs_config: config.FsConfig, operation: telegram.OperationCtx, pb: ProgressBar):
        operation.add(File(fs_config.get_path(file_path), file_path, pb))


class Get(FileCommand):
    command_name = "get"
    command_help = "Get file from telegram"
    must_exist = False
    
    @classmethod
    async def exec(cls, client: pyrogram.Client, file_path: str, app_config: config.AppConfig, fs_config: config.FsConfig, operation: telegram.OperationCtx, pb: ProgressBar):
        operation.get(File(fs_config.get_path(file_path), file_path, pb))


class Rm(FileCommand):
    command_name = "rm"
    command_help = "Remove file from telegram"
    must_exist = False
    expect_dirs = True
    
    @classmethod
    async def exec(cls, client: pyrogram.Client, file_path: str, app_config: config.AppConfig, fs_config: config.FsConfig, operation: telegram.OperationCtx, pb: ProgressBar):
        operation.delete(File(fs_config.get_path(file_path), file_path, pb))


class IndexEditingCommand(Command, abc.ABC):
    flags: dict[str, dict[str, typing.Any]] = {}
    command_name: str | None = None
    command_help: str | None = None
    
    @classmethod
    def edit_argparser(cls, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        if cls.command_name is None or cls.command_help is None:
            raise NotImplemented
        arg = parser.add_parser(cls.command_name, description=cls.command_help)
        for flag, args in cls.flags.items():
            arg.add_argument(f"--{flag}", **args)
        return arg
    
    @classmethod
    @abc.abstractclassmethod
    async def exec(cls, client: pyrogram.Client, app_config: config.AppConfig, **args: typing.Any):
        pass
    
    @classmethod
    async def run(cls, client: pyrogram.Client, args: argparse.Namespace, app_config: config.AppConfig, fs_config: config.FsConfig | None):
        kwargs = {argname: getattr(args, argname) for argname in cls.flags}
        await cls.exec(client, app_config, **kwargs)


class Init(Command):
    
    @classmethod
    def edit_argparser(cls, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        arg = parser.add_parser("init", description="Init index here")
        arg.add_argument("index_name", help="Name of new fs")
        arg.add_argument("--id", help="Id of chat to add index to, may be username", default="me")
        return arg
    
    @classmethod
    async def run(cls, client: pyrogram.Client, args: argparse.Namespace, app_config: config.AppConfig, fs_config: config.FsConfig | None):
        if fs_config and os.path.abspath(os.getcwd()) == fs_config.dir_path:
            raise exceptions.CommandValidationError("Index already exists")
        fs_config = config.FsConfig(
            session=client.session_name,
            index_name=args.index_name,
            chat_id=args.id,
            dir_path=os.path.abspath(os.getcwd())
        )
        
        with open(os.path.join(os.getcwd(), config.FS_FILE_NAME), "w") as f:
            json.dump(fs_config.dict(), f)
        
        index = telegram.FileSystemIndex(
            index_name=args.index_name,
            files={}
        )
        await index.save(client, args.id)


class Clone(Command):
    
    @classmethod
    def edit_argparser(cls, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        arg = parser.add_parser("clone", description="Init index here")
        arg.add_argument("old_index_name", help="Name of old fs")
        arg.add_argument("new_index_name", help="Name of new fs")
        arg.add_argument("--from_id", help="Id of chat to get index from, may be username", default="me")
        arg.add_argument("--to_id", help="Id of chat to add index to, may be username", default="me")
        return arg
    
    @classmethod
    async def run(cls, client: pyrogram.Client, args: argparse.Namespace, app_config: config.AppConfig, fs_config: config.FsConfig | None):
        if fs_config and os.path.abspath(os.getcwd()) == fs_config.dir_path:
            raise exceptions.CommandValidationError("Index already exists")
        
        telegram_api = telegram.TelegramApi(client)
        
        old_fs = await telegram.TelegramFileSystem.with_telegram_api(
            telegram_api,
            client, args.from_id, args.old_index_name
        )
        
        progress_bar = ProgressBar()
        
        async with old_fs.operation() as op:
            for file_name in old_fs.files:
                op.get(File(file_name, os.path.join(os.path.abspath(os.getcwd()), file_name), progress_bar))
        
        new_index = telegram.FileSystemIndex(
            index_name=args.new_index_name,
            files={}
        )
        await new_index.save(client, args.to_id)
        
        fs_config = config.FsConfig(
            session=client.session_name,
            index_name=args.new_index_name,
            chat_id=args.to_id,
            dir_path=os.path.abspath(os.getcwd())
        )
        
        with open(os.path.join(os.path.curdir, config.FS_FILE_NAME), "w") as f:
            json.dump(fs_config.dict(), f)
        
        new_fs = telegram.TelegramFileSystem(
            telegram_api,
            new_index,
            args.to_id,
            client
        )
        
        progress_bar = ProgressBar()
        
        async with new_fs.operation() as op:
            for file_name in old_fs.files:
                op.add(File(file_name, fs_config.get_path(file_name), progress_bar))


def get_differs_files(fs: telegram.TelegramFileSystem, fs_config: config.FsConfig) -> tuple[set[str], set[str]]:
    differs = set()
    deleted = set()
    
    for filepath in fs.files:
        telegram_file = fs.get_file_from_local_index(filepath)
        if telegram_file is None:
            raise exceptions.CommandValidationError("Internal error: Cannot be raised")
        current_filepath = os.path.join(fs_config.dir_path, filepath)
        if not os.path.exists(current_filepath):
            deleted.add(filepath)
            continue
        if utils.hash_file(current_filepath) != telegram_file.filehash:
            differs.add(filepath)
    
    return differs, deleted


class Status(Command):
    @classmethod
    def edit_argparser(cls, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        arg = parser.add_parser("status", description="Get status of current index")
        return arg
    
    @classmethod
    async def run(cls, client: pyrogram.Client, args: argparse.Namespace, app_config: config.AppConfig, fs_config: config.FsConfig | None):
        if fs_config is None:
            raise exceptions.WrongIndexException("Index not found")
        fs = await telegram.TelegramFileSystem.with_telegram_api(
            telegram.TelegramApi(client),
            client,
            fs_config.chat_id,
            fs_config.index_name
        )
        
        print(f"Currently in index `{fs_config.index_name}`:")
        print(f"    Chat id: `{fs_config.chat_id}`")
        print(f"    Working directory: `{fs_config.dir_path}`")
        print(f"    Session in file: {fs_config.session}")
        
        differs, deleted = get_differs_files(fs, fs_config)
           
        if not differs and not deleted:
            print("\nAll files are up-to-date")
            return
        
        if differs:
            print("\nFile modified:")
            for filepath in differs:
                print(f"    {filepath}")
            
        if deleted:
            print("\nFile deleted:")
            for filepath in deleted:
                print(f"    {filepath}")


class Download(Command):
    @classmethod
    def edit_argparser(cls, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        arg = parser.add_parser("download", description="Download all modified files")
        return arg

    @classmethod
    async def run(cls, client: pyrogram.Client, args: argparse.Namespace, app_config: config.AppConfig, fs_config: config.FsConfig | None):
        if fs_config is None:
            raise exceptions.WrongIndexException("Index not found")
        fs = await telegram.TelegramFileSystem.with_telegram_api(
            telegram.TelegramApi(client),
            client,
            fs_config.chat_id,
            fs_config.index_name
        )
        differs, deleted = get_differs_files(fs, fs_config)
        
        pb = ProgressBar(name="Syncing")
        async with fs.operation() as op:
            for filepath in differs | deleted:
                current_path = os.path.join(fs_config.dir_path, filepath)
                f = File(filepath, current_path, pb)
                op.get(f)


class Upload(Command):
    @classmethod
    def edit_argparser(cls, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        arg = parser.add_parser("upload", description="Upload all modified files")
        return arg

    @classmethod
    async def run(cls, client: pyrogram.Client, args: argparse.Namespace, app_config: config.AppConfig, fs_config: config.FsConfig | None):
        if fs_config is None:
            raise exceptions.WrongIndexException("Index not found")
        fs = await telegram.TelegramFileSystem.with_telegram_api(
            telegram.TelegramApi(client),
            client,
            fs_config.chat_id,
            fs_config.index_name
        )
        differs, deleted = get_differs_files(fs, fs_config)
        
        pb = ProgressBar(name="Uploading")
        async with fs.operation() as op:
            for filepath in differs:
                current_path = os.path.join(fs_config.dir_path, filepath)
                f = File(filepath, current_path, pb)
                op.add(f)
            
            for filepath in deleted:
                current_path = os.path.join(fs_config.dir_path, filepath)
                f = File(filepath, current_path, pb)
                op.delete(f)
    