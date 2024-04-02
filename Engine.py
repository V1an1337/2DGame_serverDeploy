import math
import random

from pymunk import Vec2d
import json, time
import os
import string
import shutil

import sys
import io
import logging

import sys
import io
import logging, time


class userIO:
    def __init__(self, identifier):
        self.identifier = identifier
        self.original_io = sys.stdout
        self.io = io.StringIO()

        self.clear()

    def switch(self):
        sys.stdout = self.io

    def recover(self):
        sys.stdout = self.original_io

    def write(self, s):
        self.io.write(s)

    def getValue(self):
        return self.io.getvalue()

    def clear(self):
        # 清空内容
        self.io.seek(0)
        self.io.truncate(0)


class userLogger:
    def __init__(self, name):
        self.userio = userIO(name)

        self.logger = logging.getLogger(f'userLogger_{name}')
        self.logger.setLevel(logging.INFO)
        fileHandler = logging.FileHandler(f'userLog/{name}_{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}.log')
        format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fileHandler.setFormatter(format)
        self.logger.addHandler(fileHandler)

    def update(self):
        value = self.userio.getValue()
        if len(value) > 1:
            self.logger.info(self.userio.getValue())
            self.userio.clear()


def format_nf(f: float, n=3):
    return float(f'%.{n}f' % f)


def angleANDradius2pos(center, angle, radius):
    x_center, y_center = center
    x_target = format_nf(x_center + radius * math.cos(angle))
    y_target = format_nf(y_center + radius * math.sin(angle))
    return (x_target, y_target)


def getFileNames():
    # 获取当前工作目录
    current_directory = "config/"

    # 获取当前目录下的所有文件和文件夹
    all_files_and_folders = os.listdir(current_directory)

    # 筛选出只有文件的项
    files_only = [file for file in all_files_and_folders if os.path.isfile(os.path.join(current_directory, file))]

    return files_only


def collide_circle(pos1, radius1, pos2, radius2):
    pos1 = Vec2d(pos1[0], pos1[1])
    pos2 = Vec2d(pos2[0], pos2[1])

    distance = pos1.get_distance(pos2)
    if distance < radius1 + radius2:
        return True
    else:
        return False


def generateLibCache(libName):
    characters = string.ascii_letters + string.digits + '_'
    code = ''.join(random.choice(characters) for _ in range(16))

    # 如果密码以下划线开头，则重新生成密码，直到密码不以下划线开头
    while code.startswith('_'):
        code = ''.join(random.choice(characters) for _ in range(16))

    original_dir = "config"
    target_dir = "cache/config"
    original_filename = f"{libName}.py"
    target_filename = f"playerLib_{code}.py"
    target_name = f"playerLib_{code}"

    copy_file(original_dir, target_dir, original_filename, target_filename)
    return target_name


def calculate_angle(coord1, coord2):
    # 计算两个坐标之间的差值
    delta_x = coord2[0] - coord1[0]
    delta_y = coord2[1] - coord1[1]

    # 计算夹角（弧度）
    angle_rad = math.atan2(delta_y, delta_x)

    # 将弧度转换为角度
    angle_deg = math.degrees(angle_rad)

    # 确保角度在 0 到 360 之间
    angle_deg %= 360

    return angle_deg


def copy_file(original_dir, target_dir, original_filename, target_filename):
    # 构建原始文件路径和目标文件路径
    original_path = os.path.join(original_dir, original_filename)
    target_path = os.path.join(target_dir, target_filename)

    # 复制文件
    shutil.copy(original_path, target_path)


class timecostLogger:
    timecosts: list
    points: dict
    lastpoint: time.time

    def __init__(self):
        self.timecosts = []
        self.points = {}

    def clear(self):
        self.timecosts.clear()
        self.points.clear()
        self.lastpoint = None

    def addPoint(self, name):
        p = time.time()
        self.points[name] = p
        self.lastpoint = name

    def endPoint(self, name):
        self.timecosts.append([name, self.calc(name)])

    def calc(self, name):
        return time.time() - self.points[name]

    def lastPoint(self):
        return self.lastpoint

    def show(self):
        return self.timecosts

    def get(self, name):
        return self.points[name]
