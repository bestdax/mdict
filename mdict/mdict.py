#!/usr/bin/env python

# mdict.py
# 本程序参考Xiaoqiang Wang的readmdict.py，在此特别致谢。
# created on 2024-11-22
from struct import pack, unpack
import zlib
import re
import html
from io import BytesIO
import lzo


class Mdict:
    def __init__(self, mdx_path: str) -> None:
        """
        初始化Mdict对象。

        Args:
            mdx_path (str): MDX文件的路径。
        """
        self._mdx_path = mdx_path
        self._header_bytes_size = 0
        self._header_bytes = None
        self._key_block_offset = 0
        self._key_block_offset = 0
        self._stylesheet = {}
        self._mdx_file = None
        self._encoding = None

        self._read_mdx_header()
        self._read_mdx_keys()

    def _read_number(self, bytes_stream: BytesIO):
        """
        读取一个4个字节无符号整数。
        :param bytes_stream:
        :return:
        """
        return unpack(self._number_format, bytes_stream.read(self._number_width))[0]

    def _read_mdx_header(self):
        """
        读取MDX文件的头部信息。

        Raises:
            FileNotFoundError: 文件不存在。
            IOError: 文件读取错误。
        """
        try:
            with open(self._mdx_path, 'rb') as mdict_file:
                # 文件头信息提取
                self._header_bytes_size = unpack('>I', mdict_file.read(4))[0]  # 开始的4个字节存储文件头信息的长度
                self._header_bytes = mdict_file.read(self._header_bytes_size)  # 读取文件头比特流

                # adler32数据校验
                adler32 = unpack('<I', mdict_file.read(4))[0]  # 以小端数存储的4位校验码
                assert adler32 == zlib.adler32(self._header_bytes) & 0xffffffff

                # 记录键开始的位置
                self._key_block_offset = mdict_file.tell()
        except FileNotFoundError:
            print(f"File {self._mdx_path} not found.")
        except IOError as e:
            print(f"Error reading file {self._mdx_path}: {e}")

        # 文件头信息的最后\x00\x00需要舍弃，内容是用utf-16编码的，需要解码，然后再转成utf-8编码
        header_text = str(self._header_bytes[:-2].decode('utf-16').encode('utf-8'))

        # 提取tag信息并转换成字典，同时将信息逆转义 (将&lt;替换成<，将&gt;替换成>等)
        tag_list = re.findall(r'(\w+)="(.*?)"', header_text, re.DOTALL)
        self._tag_dict = {key: html.unescape(value) for key, value in tag_list}

        # 现在UTF-8的编码已经非常普遍，所以不对编码进行任何处理

        # 读取标题和描述
        self._title = self._tag_dict['title'] if 'title' in self._tag_dict else ''
        self._description = self._tag_dict['Description'] if 'Description' in self._tag_dict else ''
        self._encoding = self._tag_dict['Encoding'] if 'Encoding' in self._tag_dict else 'UTF-8'

        # 读取加密信息
        # 0：没有加密。
        # 1：关键词头被加密。
        # 2：关键词索引被加密。
        # 3：关键词头和关键词索引都被加密。这是上述两种加密的组合。
        self._encrypted = self._tag_dict['encrypted'] if 'encrypted' in self._tag_dict else 0

        # 摘自mdxbuilder文档
        # 记号文件的格式：
        # 由多个记号定义组成，每个记号定义有3行
        # 第一行: 记号的名称(只能用数字，必须大于0，最大不超过255)
        # 第二行: 开始字符串(可以为空)
        # 第三行: 结束字符串(可以为空)
        # 使用时在正文里使用`记号`(键盘左上角的那个符号)就会将后续的文字直到下一个记号前的文
        # 字用记号定义的开始字符串和结束字符串括起来。正文里如果需要显示` 则用"&#96;"表示。内
        # 码应该和正文的一样(例如正文如果是用Unicode的话，记号文件也应该用Unicode)
        #
        # 例如：
        # 记号文件：
        # 1
        # <font size=5>
        # </font>
        # 2
        # <br>
        #
        # 3
        # <font face="Kingsoft Phonetic Plain, Tahoma">
        # </font>
        # 这个样式单我觉得不太实际，编写起来太麻烦了

        if self._tag_dict.get('Stylesheet') is not None:
            lines = self._tag_dict['Stylesheet'].split()
            for row in range(0, len(lines), 3):
                self._stylesheet[lines[row]] = lines[row + 1:row + 3]

        # 版本2.0之前数字的宽度是4个字节，>=2.0的版本是8个字节
        self._version = float(self._tag_dict['GeneratedByEngineVersion'])
        if self._version < 2.0:
            self._number_width = 4
            self._number_format = '>I'
        else:
            self._number_width = 8
            self._number_format = '>Q'

    def _read_mdx_keys(self) -> list:
        with open(self._mdx_path, 'rb') as mdict_file:
            mdict_file.seek(self._key_block_offset)

            if self._version < 2.0:
                number_bytes = self._number_width * 4
            else:
                number_bytes = self._number_width * 5

            block = mdict_file.read(number_bytes)

            # 不支持加密的MDX文件
            if self._encrypted != 0:
                raise NotImplementedError('不支持加密的MDX文件')

            bytes_stream = BytesIO(block)

            # 读取键区块的数量
            number_of_key_blocks = self._read_number(bytes_stream)
            # 读取词条的数量
            self._number_of_entries = self._read_number(bytes_stream)
            # 在2.0版本及之后，block的第三段存储键区块信息解压后的字节数
            if self._version >= 2.0:
                key_block_info_decompressed_size = self._read_number(bytes_stream)
            # 键区块信息的解压缩之前的字节数
            key_block_info_compressed_size = self._read_number(bytes_stream)
            # 键区块的字节数
            key_block_size = self._read_number(bytes_stream)

            # 2.0版本及之后，下面的4个字节是前面5个字节的adler32校验码
            if self._version >= 2.0:
                adler32 = unpack('>I', mdict_file.read(4))[0]  # 以大端数存储的4位校验码
                assert adler32 == zlib.adler32(block) & 0xffffffff

            key_block_info = mdict_file.read(key_block_info_compressed_size)
            key_block_info_list = self._decode_key_block_info(key_block_info)
            assert len(key_block_info_list) == number_of_key_blocks

            # 读取键区块
            key_block_compressed = mdict_file.read(key_block_size)
            key_list = self._decode_key_block(key_block_compressed, key_block_info_list)

            self._key_block = mdict_file.tell()

        return key_list

    def _decode_key_block(self, key_block_compressed: bytes, key_block_info_list: list) -> list:
        """
        解码压缩的键区块。
        """
        key_list = []
        key_offset = 0
        key_block = b''

        for compressed_size, decompressed_size in key_block_info_list:
            start = key_offset
            end = start + compressed_size

            # 最开始的4个字节为压缩类型
            key_block_type = key_block_compressed[start: start + 4]
            # 第二个4个字节为adler32校验码
            adler32 = unpack('>I', key_block_compressed[start + 4:start + 8])[0]

            if key_block_type == b'\x00\x00\x00\x00':
                key_block = key_block_compressed[start + 8:end]
            elif key_block_type == b'\x01\x00\x00\x00':
                key_block = lzo.decompress(key_block_compressed[start + 8:end])
            elif key_block_type == b'\x02\x00\x00\x00':
                try:
                    key_block = zlib.decompress(key_block_compressed[start + 8:end])
                except zlib.error as e:
                    print(f'压缩数据解压失败: {e}')
            else:
                raise NotImplementedError('不支持该压缩类型')

            key_list.extend(self._split_key_block(key_block))

            assert adler32 == zlib.adler32(key_block) & 0xffffffff

            key_offset += compressed_size

        return key_list

    def _split_key_block(self, key_block: bytes) -> list:
        """
        将输入的字符串按照指定的分隔符分割成多个块。

        该函数接收key_block的字节流作为输入，并返回一个(key_id, key_text)的列表。

        参数：
            key_block (bytes): 需要被分割成块的bytes。

        返回：
            list: (key_id: int, key_text: bytes)的列表。
        """
        key_list = []
        key_start_index = 0

        while key_start_index < len(key_block):
            temp = key_block[key_start_index:key_start_index + self._number_width]
            key_id = unpack(self._number_format, temp)[0]

            # 键值文本以\x00结尾
            if self._encoding == 'UTF-16':
                delimiter = b'\x00\x00'
                width = 2
            else:
                delimiter = b'\x00'
                width = 1

            i = key_start_index + self._number_width

            key_end_index = 0
            while i < len(key_block):
                if key_block[i: i + width] == delimiter:
                    key_end_index = i
                    break
                i += width
            if key_end_index:
                key_text = key_block[key_start_index + self._number_width:key_end_index] \
                    .decode(self._encoding, errors='ignore').encode('utf-8').strip()
                key_start_index = key_end_index + width
                key_list += [(key_id, key_text)]

        return key_list

    def _decode_key_block_info(self, key_block_info_compressed: bytes) -> list:
        """
        解码压缩的键区块信息。

        该函数负责将压缩的键区块信息解压，并验证其完整性。它首先检查压缩数据的头部，以确定其版本和有效性。
        如果版本高于2.0，它将使用 zlib 库进行解压，并验证解压后数据的 Adler-32 校验码。
        然后，根据版本不同，使用不同的格式解析键区块信息中的条目数量。

        参数：
        key_block_info_compressed (bytes): 压缩的键区块信息数据。

        返回：
        None

        异常：
        AssertionError: 如果压缩数据的头部不匹配预期的版本标记，或者 Adler-32 校验码不匹配。

        注意：
        该函数假设传入的 key_block_info_compressed 是有效的压缩数据，且版本标记和校验码正确。
        该函数不返回任何值，而是直接修改类的内部状态。

        依赖：
        zlib: 用于解压压缩数据。
        struct: 用于解析二进制数据。
        """
        if self._version > 2.0:
            assert key_block_info_compressed[:4] == b'\x00\x00\x00\x02'

            key_block_info = zlib.decompress(key_block_info_compressed[8:])
            adler32 = unpack('>I', key_block_info_compressed[4:8])[0]  # 以大端数存储的4位校验码
            assert adler32 == zlib.adler32(key_block_info) & 0xffffffff
        else:
            key_block_info = key_block_info_compressed

        # 解码
        key_block_info_list = []
        number_of_entries = 0
        if self._version >= 2:
            byte_format = '>H'  # 大端2个字节无符号整数
            byte_width = 2
            text_term = 1
        else:
            byte_format = '>B'  # 大端1个字节无符号整数
            byte_width = 1
            text_term = 0

        key_offset = 0

        while key_offset < len(key_block_info):
            # 当前区块中的词条数量
            number_of_entries += \
                unpack(self._number_format, key_block_info[key_offset:key_offset + self._number_width])[
                    0]
            key_offset += self._number_width

            # 文本头部长度
            text_head_size = unpack(byte_format, key_block_info[key_offset:key_offset + byte_width])[0]
            key_offset += byte_width

            # 文本头部
            if self._encoding != 'UTF-16':
                key_offset += text_head_size + text_term
            else:
                key_offset += (text_head_size + text_term) * 2

            # 文本尾部长度
            text_tail_size = unpack(byte_format, key_block_info[key_offset:key_offset + byte_width])[0]
            key_offset += byte_width

            # 文本尾部
            if self._encoding != 'UTF-16':
                key_offset += text_tail_size + text_term
            else:
                key_offset += (text_tail_size + text_term) * 2

            # 键区块的压缩后的字节数
            key_block_compressed_size = \
                unpack(self._number_format, key_block_info[key_offset:key_offset + self._number_width])[0]
            key_offset += self._number_width

            # 键区块的解压后的字节数
            key_block_decompressed_size = \
                unpack(self._number_format, key_block_info[key_offset:key_offset + self._number_width])[0]
            key_offset += self._number_width
            key_block_info_list.append((key_block_compressed_size, key_block_decompressed_size))

        assert number_of_entries == self._number_of_entries
        return key_block_info_list


if __name__ == '__main__':
    mdict = Mdict('/Users/dax/Documents/Personal/Dictionary/牛津高阶9/牛津高阶英汉双解词典(第9版)_V3.1.2版.mdx')
