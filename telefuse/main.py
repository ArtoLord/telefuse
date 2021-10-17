import telegram
import config
import pyrogram
import os
from pathlib import Path
import abstract
import argparse
import telefs
import json


class File(abstract.File):
    def __init__(self, path, real_path) -> None:
        self.path = path
        self.name = os.path.basename(path)
        self.real_path = real_path
    
    @classmethod
    async def form_path(cls, path):
        return cls(path, path)


async def main(client: pyrogram.Client):
    fs = await telegram.TelegramFileSystem.with_telegram_api(
        telegram.TelegramApi(client),
        client,
        "me",
        "SOME_INDEX_PREFIX"
    )

async def init(client: pyrogram.Client, args: argparse.Namespace):
    chat_id = args.id
    
    config = telefs.FsConfig(
        session=client.session_name,
        index_name=args.index_name,
        chat_id=chat_id,
        dir_path=os.path.abspath(os.path.curdir)
    )
    
    with open(os.path.join(os.path.curdir, telefs.FS_FILE_NAME), "w") as f:
        json.dump(config.dict(), f)
    
    index = telegram.FileSystemIndex(
        index_name=args.index_name,
        files={}
    )
    await index.save(client, chat_id)


async def add(client: pyrogram.Client, args: argparse.Namespace):
    
    path = os.path.abspath(args.path)
    
    config = telefs.FsConfig.find(os.path.abspath(os.curdir))
    
    fs = await telegram.TelegramFileSystem.with_telegram_api(
        telegram.TelegramApi(client),
        client,
        config.chat_id,
        config.index_name
    )
    
    await fs.init_file(File(config.get_path(path), path))


async def rm(client: pyrogram.Client, args: argparse.Namespace):
    
    path = os.path.abspath(args.path)
    
    config = telefs.FsConfig.find(os.path.abspath(os.curdir))
    
    fs = await telegram.TelegramFileSystem.with_telegram_api(
        telegram.TelegramApi(client),
        client,
        config.chat_id,
        config.index_name
    )
    
    await fs.remove_file(File(config.get_path(path), path))


async def get(client: pyrogram.Client, args: argparse.Namespace):
    
    path = os.path.abspath(args.path)
    
    config = telefs.FsConfig.find(os.path.abspath(os.curdir))
    
    fs = await telegram.TelegramFileSystem.with_telegram_api(
        telegram.TelegramApi(client),
        client,
        config.chat_id,
        config.index_name
    )
    
    await fs.get_file(File(config.get_path(path), path))
    

def start_telegram_client(app_config: config.AppConfig, session: str) -> pyrogram.Client:
    return pyrogram.Client(
        session,
        api_id=app_config.api_id,
        api_hash=app_config.api_hash,
    )


def init_parsers() -> argparse.Namespace:
    main_parser = argparse.ArgumentParser()
    main_parser.add_argument("-s", "--session", default=os.path.join(Path.home(), ".telefuze_session"))
    
    subparsers = main_parser.add_subparsers()
    
    init_parser = subparsers.add_parser("init", description="Initialize telegram fs here", )
    init_parser.add_argument("index_name", help="Name of an new or existing fs")
    init_parser.add_argument("--id", help="Id of chat to add index to, may be username", default="me")
    init_parser.set_defaults(func=init, name="init")
    
    add_parser = subparsers.add_parser("add", description="Add file to telegram fs", )
    add_parser.add_argument("path", help="Path of file to add")
    add_parser.set_defaults(func=add, name="add")
    
    add_parser = subparsers.add_parser("get", description="Get file from telegram fs", )
    add_parser.add_argument("path", help="Path of file to get")
    add_parser.set_defaults(func=add, name="add")
    
    add_parser = subparsers.add_parser("rm", description="Rm file from telegram fs", )
    add_parser.add_argument("path", help="Path of file to rm")
    add_parser.set_defaults(func=rm, name="rm")
    
    return main_parser.parse_args()


if __name__ == '__main__':
    
    try:
        fs_config = telefs.FsConfig.find(os.path.abspath(os.curdir))
    except telefs.FsNotFoundException:
        fs_config = None
    
    args = init_parsers()
    
    session = args.session if not fs_config else fs_config.session
    
    app_config = config.AppConfig()
    client = start_telegram_client(app_config, args.session)
    client.run(args.func(client, args))
