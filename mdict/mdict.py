#!/usr/bin/env python

# mdict.py
# 本程序参考Xiaoqiang Wang的readmdict.py，在此特别致谢。
# created on 2024-11-22
from struct import pack, unpack
import zlib


class Mdict:
    def __init__(self, mdx_path: str) -> None:
        self.mdx_path = mdx_path
        self.header_bites_size = 0
        self.header_bites = None
        self.key_block_offset = 0

    def read_mdx_head(self):
        with open(self.mdx_path, 'rb') as mdict_file:
            # 文件头信息提取
            self.header_bites_size = unpack('>I', mdict_file.read(4))[0]  # 开始的4个字节存储文件头信息的长度
            self.header_bites = mdict_file.read(self.header_bites_size)  # 读取文件头比特流

            # adler32数据校验
            adler32 = unpack('<I', mdict_file.read(4))[0]  # 以小端数存储的4位校验码
            assert adler32 == zlib.adler32(self.header_bites) & 0xffffffff

            # 记录键开始的位置
            self.key_block_offset = mdict_file.tell()
            mdict_file.close()


if __name__ == '__main__':
    mdict = Mdict('/Users/dax/Documents/Personal/Dictionary/牛津高阶9/牛津高阶英汉双解词典(第9版)_V3.1.2版.mdx')
    mdict.read_mdx_head()
    print(mdict.header_bites)
