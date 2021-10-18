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


class File(abstract.File):
    def __init__(self, path, real_path) -> None:
        self.path = path
        self.name = os.path.basename(path)
        self.real_path = real_path


class Command(abc.ABC):
    
    def __init__(self, client: pyrogram.Client, parser: argparse._SubParsersAction, app_config: config.AppConfig, fs_config: config.FsConfig | None) -> None:
        def exec(args: argparse.Namespace):
            return self.run(client, args, app_config, fs_config)
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
        Clone
    ]
    
    return [
        command(client, parser, app_config, fs_config) for command in commands
    ]


class FileCommand(Command, abc.ABC):
    command_name: str | None = None
    command_help: str | None = None
    
    @classmethod
    def edit_argparser(cls, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        if cls.command_name is None or cls.command_help is None:
            raise NotImplemented
        arg = parser.add_parser(cls.command_name, description=cls.command_help)
        arg.add_argument("files", help=f"Path of file for {cls.command_name}", nargs="+")
        return arg
    
    @classmethod
    @abc.abstractclassmethod
    async def exec(cls, client: pyrogram.Client, file_path:str, app_config: config.AppConfig, fs_config: config.FsConfig, fs: telegram.TelegramFileSystem):
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
        for file_path in args.files:
            if not os.path.isfile(file_path) or not os.path.exists(file_path):
                raise exceptions.CommandValidationError(f"File {file_path} is not walid")
            await cls.exec(
                client, file_path, app_config, fs_config, fs
            )
    
    
class Add(FileCommand):
    command_name = "add"
    command_help = "Add file to index and upload it to telegram"
    
    @classmethod
    async def exec(cls, client: pyrogram.Client, file_path: str, app_config: config.AppConfig, fs_config: config.FsConfig, fs: telegram.TelegramFileSystem):
        await fs.init_file(File(fs_config.get_path(file_path), file_path))


class Get(FileCommand):
    command_name = "get"
    command_help = "Get file from telegram"
    
    @classmethod
    async def exec(cls, client: pyrogram.Client, file_path: str, app_config: config.AppConfig, fs_config: config.FsConfig, fs: telegram.TelegramFileSystem):
        await fs.get_file(File(fs_config.get_path(file_path), file_path))


class Rm(FileCommand):
    command_name = "rm"
    command_help = "Remove file from telegram"
    
    @classmethod
    async def exec(cls, client: pyrogram.Client, file_path: str, app_config: config.AppConfig, fs_config: config.FsConfig, fs: telegram.TelegramFileSystem):
        await fs.remove_file(File(fs_config.get_path(file_path), file_path))


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
        
        for file_name in old_fs.files:
            await old_fs.get_file(File(file_name, os.path.join(os.path.abspath(os.getcwd()), file_name)))
        
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
        
        for file_name in old_fs.files:
            await new_fs.init_file(File(file_name, fs_config.get_path(file_name)))
