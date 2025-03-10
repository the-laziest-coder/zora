import os
import json
import asyncio
from copy import deepcopy
from typing import Optional

from ..models import AccountInfo


class Storage:

    def __init__(self, filename: str):
        self.filename = filename
        self.data = {}
        self.lock = asyncio.Lock()

    def init(self):
        if not os.path.exists(self.filename):
            self.data = {}
            return
        with open(self.filename, 'r', encoding='utf-8') as file:
            if len(file.read().strip()) == 0:
                self.data = {}
                return
        with open(self.filename, 'r', encoding='utf-8') as file:
            converted_data = json.load(file)
        backup_filename = self.filename.split('/')[-1]
        with open('.backup/' + backup_filename, 'w', encoding='utf-8') as backup_file:
            json.dump(converted_data, backup_file, indent=2)
        self.data = converted_data

    def get_final_value(self, key: str):
        value = self.data.get(key)
        if value is None:
            return None
        return deepcopy(value)

    def set_final_value(self, key: str, value):
        self.data[key] = deepcopy(value)

    def remove(self, key: str):
        if key in self.data:
            self.data.pop(key)

    async def get_value(self, key: str):
        async with self.lock:
            return self.get_final_value(key)

    async def set_value(self, key: str, value):
        async with self.lock:
            self.set_final_value(key, value)

    async def async_save(self):
        async with self.lock:
            self.save()

    def save(self):
        self._save(self.data)

    def _save(self, converted_data):
        js_dump = self._transform(converted_data)
        with open(self.filename, 'w', encoding='utf-8') as file:
            file.write(js_dump)

    @classmethod
    def _transform(cls, json_obj, indent=2):
        def inner_transform(o):
            if isinstance(o, list) or isinstance(o, tuple):
                for v in o:
                    if isinstance(v, dict):
                        return [inner_transform(v) for v in o]
                return "#!#<{}>#!#".format(json.dumps(o))
            elif isinstance(o, dict):
                return {k: inner_transform(v) for k, v in o.items()}
            return o

        if isinstance(json_obj, dict):
            transformed = {k: inner_transform(v) for k, v in json_obj.items()}
        elif isinstance(json_obj, list) or isinstance(json_obj, tuple):
            transformed = [inner_transform(v) for v in json_obj]
        else:
            transformed = inner_transform(json_obj)

        transformed_json = json.dumps(transformed, indent=indent)
        transformed_json = transformed_json.replace('"#!#<', "").replace('>#!#"', "").replace('\\"', "\"")

        return transformed_json


class AccountStorage(Storage):

    def __init__(self, filename: str):
        super().__init__(filename)

    def init(self):
        super().init()
        self.data = {a: AccountInfo.from_dict(i) for a, i in self.data.items()}

    def get_final_account_info(self, address: str) -> Optional[AccountInfo]:
        return self.get_final_value(address)

    def set_final_account_info(self, address: str, info: AccountInfo):
        return self.set_final_value(address, info)

    async def get_account_info(self, address: str) -> Optional[AccountInfo]:
        return await self.get_value(address)

    async def set_account_info(self, address: str, info: AccountInfo):
        await self.set_value(address, info)

    async def async_save(self):
        await super().async_save()

    def save(self):
        converted_data = {a: i.to_dict() for a, i in self.data.items()}
        super()._save(converted_data)
