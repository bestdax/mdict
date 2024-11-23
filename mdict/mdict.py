#!/usr/bin/env python

# mdict.py
# 本程序参考Xiaoqiang Wang的readmdict.py，在此特别致谢。
# created on 2024-11-22
from struct import pack, unpack
import zlib
import re
import html


class Mdict:
    def __init__(self, mdx_path: str) -> None:
        """
        初始化Mdict对象。

        Args:
            mdx_path (str): MDX文件的路径。
        """
        self.mdx_path = mdx_path
        self.header_bites_size = 0
        self.header_bites = None
        self.key_block_offset = 0
        self.stylesheet = {}

    def _read_mdx_head(self):
        """
        读取MDX文件的头部信息。

        Raises:
            FileNotFoundError: 文件不存在。
            IOError: 文件读取错误。
        """
        try:
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
        except FileNotFoundError:
            print(f"File {self.mdx_path} not found.")
        except IOError as e:
            print(f"Error reading file {self.mdx_path}: {e}")

        # 文件头信息的最后\x00\x00需要舍弃，内容是用utf-16编码的，需要解码，然后再转成utf-8编码
        header_text = str(self.header_bites[:-2].decode('utf-16').encode('utf-8'))

        # 提取tag信息并转换成字典，同时将信息逆转义 (将&lt;替换成<，将&gt;替换成>等)
        tag_list = re.findall(r'(\w+)="(.*?)"', header_text, re.DOTALL)
        tag_dict = {key: html.unescape(value) for key, value in tag_list}

        # 现在utf-8编码已经非常普遍，所以不对编码进行任何处理

        # 读取标题和描述
        self.title = tag_dict['title'] if 'title' in tag_dict else ''
        self.description = tag_dict['Description'] if 'Description' in tag_dict else ''

        # 读取加密信息
        # 0：没有加密。
        # 1：关键词头被加密。
        # 2：关键词索引被加密。
        # 3：关键词头和关键词索引都被加密。这是上述两种加密的组合。
        self._encrypted = tag_dict['encrypted'] if 'encrypted' in tag_dict else 0

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

        if tag_dict.get('Stylesheet') is not None:
            lines = tag_dict['Stylesheet'].split()
            for row in range(0, len(lines), 3):
                self.stylesheet[lines[row]] = lines[row + 1:row + 3]

        # 版本2.0之前数字的宽度是4个字节，>=2.0的版本是8个字节
        self._version = float(tag_dict['GeneratedByEngineVersion'])
        if self._version < 2.0:
            self._number_width = 4
            self._number_format = '>I'
        else:
            self._number_width = 8
            self._number_format = '>Q'


if __name__ == '__main__':
    mdict = Mdict('/Users/dax/Documents/Personal/Dictionary/牛津高阶9/牛津高阶英汉双解词典(第9版)_V3.1.2版.mdx')
    mdict._read_mdx_head()
