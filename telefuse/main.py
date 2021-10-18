from . import config
import pyrogram
import os
from pathlib import Path
import argparse
from . import commands


def start_telegram_client(app_config: config.AppConfig, session: str) -> pyrogram.Client:
    return pyrogram.Client(
        session,
        api_id=app_config.api_id,
        api_hash=app_config.api_hash,
    )


def main():
    try:
        fs_config = config.FsConfig.find(os.path.abspath(os.getcwd()))
    except config.FsNotFoundException:
        fs_config = None
    
    args = argparse.ArgumentParser()
    app_config = config.AppConfig()
    session = os.path.join(Path.home(), ".telefs_session") if not fs_config else fs_config.session
    client = start_telegram_client(app_config, session)
    
    commands.init_commands(client, args.add_subparsers(), app_config, fs_config)
    
    args = args.parse_args()
    
    try:
        client.run(args.func(args))
    except AttributeError:
        print("Wrong command. Run with --help to see help")


if __name__ == '__main__':
    main()