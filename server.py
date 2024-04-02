import pygame
import pymunk
import websockets
import asyncio
import json
import time
import copy
import random
from Engine import *
from typing import Union
import logging
import traceback
import ast
import config.default as default

pygame.init()

# 创建两个记录器
mainLogger = logging.getLogger('mainLogger')

# 配置第一个记录器
mainLogger.setLevel(logging.INFO)
mainLogger_fileHandler = logging.FileHandler(f'log/{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}.log')
mainLogger_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
mainLogger_fileHandler.setFormatter(mainLogger_format)
mainLogger.addHandler(mainLogger_fileHandler)

mainLogger.info("logger init success")

timeLogger = timecostLogger()

mainLogger.info("timecostLogger init success")

gunType2name = {1: "machineGun", 2: "rifle", 3: "sniper", 4: "grenade", 5: "fire", 6: "RPG", 7: "pistol", 8: "xm1014"}
gunType2Position = {1: 0, 2: 0, 3: 0, 4: 3, 5: 4, 6: 2, 7: 1, 8: 0}

ERRORTIMES_JUDGE = 0


def map_image_sandbox(map_image: pygame.surface.Surface):
    new = map_image.copy()
    return new


class Room:
    state2name = {1: "warmup", 2: "round start / preparing", 3: "in a round", 4: "round end / ending"}

    def __init__(self):
        self.state = 1  # {1: warmup, 2: round start / preparing , 3: in a round, 4: round end / ending}
        self.maintainTime = 0

        self.warmupTime = int(5 * fps)
        self.roundStartTime = int(10 * fps)
        self.roundTime = int(2 * 60 * fps)
        self.roundEndTime = int(6 * fps)

        self.teamScores = {1: 0, 2: 0}

        self.warmup()

    def warmup(self):
        self.state = 1
        self.maintainTime = self.warmupTime
        for currentPlayer in Players.values():
            currentPlayer: Player
            if type(currentPlayer.weaponList[2]) != Weapon_sniper:
                currentPlayer.generate_weaponList()
            if currentPlayer.weaponList[3] == None:
                currentPlayer.weaponList[3] = Grenade_grenade(currentPlayer)
            if currentPlayer.weaponList[4] == None:
                currentPlayer.weaponList[4] = Grenade_fire(currentPlayer)

    def roundStart(self):
        global grenades, bullets, kunais
        grenades.clear()
        bullets.clear()
        kunais.clear()
        self.state = 2
        self.maintainTime = self.roundStartTime
        awaitingMessage.append(json.dumps({"type": "roundStart"}))

    def round(self):
        self.state = 3
        self.maintainTime = self.roundTime
        for currentPlayer in Players.values():
            currentPlayer: Player
            currentPlayer.reborn_defend_tick = 1

    def roundEnd(self, winningTeam=0):
        self.state = 4
        self.maintainTime = self.roundEndTime

        if winningTeam == 1:
            self.teamScores[1] += 1
        elif winningTeam == 2:
            self.teamScores[2] += 1

        awaitingMessage.append(json.dumps({"type": "scores", "scores": f"{self.teamScores[1]}|{self.teamScores[2]}"}))

        maxKill = 0
        mvpPlayer = None
        for currentPlayer in Players.values():
            currentPlayer: Player
            killedTimes = len(currentPlayer.killedList)
            if killedTimes > maxKill and currentPlayer.team == winningTeam:
                maxKill = killedTimes
                mvpPlayer = currentPlayer

            if currentPlayer.team == winningTeam:
                currentPlayer.money += 2000
            else:
                currentPlayer.money += 1500

        if mvpPlayer:
            mvpPlayer.money += 400
            awaitingMessage.append(json.dumps({"type": "mvp", "name": mvpPlayer.name, "code": mvpPlayer.MVPCode}))

    def nextState(self):
        if self.state == 1:  # warmup -> start
            self.roundStart()
            for currentPlayer in Players.values():
                currentPlayer: Player
                currentPlayer.money = 0
                currentPlayer.generate_weaponList()
        elif self.state == 2:
            self.round()
        elif self.state == 3:
            self.roundEnd()
        elif self.state == 4:
            self.roundStart()

    def update(self):
        if self.maintainTime >= 1:
            self.maintainTime -= 1
        else:
            self.nextState()

        if self.state == 1 or self.state == 4:  # warmup / ending
            for currentPlayer in Players.values():
                currentPlayer: Player
                currentPlayer.reborn_defend_tick = currentPlayer.reborn_defend_tick_constant

        rebootTime = 10
        if self.state == 2 and self.maintainTime % rebootTime == 0 and self.maintainTime > self.roundStartTime - rebootTime - 1:
            for currentPlayer in Players.values():
                currentPlayer: Player
                currentPlayer.reborn()

        if tickcount % fps == 0:
            awaitingMessage.append(json.dumps({"type": "roundInfo", "state": self.state, "time": self.maintainTime}))

    def reset(self):
        self.warmup()


class Player_kill:
    by: str
    hit: str
    killedTime: int
    pos: tuple

    def __init__(self, by, hit, killedTime, pos):
        self.by = by
        self.hit = hit
        self.killedTime = killedTime
        self.pos = pos


class Player:
    lib: any
    logger: userLogger

    body: pymunk.Body
    hp: int
    team: int
    name: str
    angle: int
    move_angle: int
    reloading: bool
    changeGun_CD: int
    changingGun: bool
    weapon_choice: int
    move_speed: float
    shifting: bool
    shift_tick: int
    reborn_defend_tick: int

    mouse_pos: Vec2d

    key_w: bool
    key_a: bool
    key_s: bool
    key_d: bool
    key_r: bool
    key_f: bool
    key_z: bool
    key_m1: bool
    key_1: bool
    key_2: bool
    key_3: bool
    key_4: bool
    key_5: bool

    radius: int
    mass: int
    moment: float
    body: pymunk.Body
    shape: pymunk.Circle

    head_pos: tuple[int, int]
    head_radius: int

    space: pymunk.space

    weapon: any
    weaponList: list

    MVPCode: int
    killedList: list[Player_kill]

    def __init__(self, name, team, MVPCode):
        self.invalid = False
        self.sandbox = None
        self.lib = default
        self.logger = userLogger(name)

        self.key_w = False
        self.key_a = False
        self.key_s = False
        self.key_d = False
        self.key_r = False
        self.key_f = False
        self.key_z = False
        self.key_m1 = False
        self.key_1 = False
        self.key_2 = False
        self.key_3 = False
        self.key_4 = False
        self.key_5 = False

        self.mouse_pos = Vec2d(0, 0)
        self.head_pos = (0, 0)
        self.angle = 0
        self.move_angle = 0
        self.hp = 100
        self.name = name
        self.reloading = False
        self.changeGun_CD = 0
        self.changingGun = False
        self.weapon_choice = 1
        self.move_speed = 0
        self.money = 0

        self.shifting = False
        self.shift_state = "normal"  # [normal, charging, releasing]
        self.shift_tick = 1
        self.shift_tick_max = 7
        self.reborn_defend_tick = 0
        self.reborn_defend_tick_constant = 3 * fps

        self.state = 1  # 0: dead, 1: normal, 2: beatBack
        self.beatBack_angle = 0
        self.beatBack_speed = move_speed_constant // 5
        self.beatBack_tick = 0
        self.beatBack_tick_constant = int(0.5 * fps)

        self.emoji = 1
        self.emojiTime = 0
        self.emojiTime_constant = int(2 * fps)

        self.killedCountTotal = 0
        self.killedList = []
        self.MVPCode = MVPCode
        self.mvp_killedPlayerNumber = 3
        self.mvp_killedTime = 30
        self.lastKillMVPProcessed = True

        self.filter = NewCollisionHandle()
        self.team = team
        self.lastMainWeapon = 1
        self.space = space

        # 创建角色
        self.radius = 20
        self.head_radius = 10
        self.mass = 1
        self.moment = pymunk.moment_for_circle(self.mass, 0, self.radius)
        self.body = pymunk.Body(self.mass, self.moment)

        self.tpSpawnpoint()

        self.shape = pymunk.Circle(self.body, self.radius)
        self.shape.elasticity = 0.1
        self.shape.filter = self.filter

        self.space.add(self.body, self.shape)
        self.generate_weaponList()
        self.chooseWeapon(2)
        self.character: Union[
            Character, Character_TimeTransferor, Character_YellowFlash, Character_RedMoonObito] = Character(self)

    def updateEmoji(self):
        if self.emojiTime > 0:
            self.emojiTime -= 1
        else:
            self.emojiTime = 0
            self.emoji = 0

    def startEmoji(self, emojiType):
        self.emoji = emojiType
        self.emojiTime = self.emojiTime_constant

    def buy(self, gunType):
        gunClass = gunType2class[gunType]
        moneyNeeded = gunClass.money
        gunPos = gunType2Position[gunType]

        if ROOM.state != 2:
            mainLogger.info(
                f"Player {self.name} try to buy weapon {gunType2name[gunType]} but failed, ROOM state = {ROOM.state}")
            return

        if self.money - moneyNeeded < 0:
            mainLogger.info(
                f"Player {self.name} try to buy weapon {gunType2name[gunType]} but failed due to not enough money, guntype = {gunType},gunPos = {gunPos}, money = {self.money}, moneyNeeded = {moneyNeeded}")
            return
        if type(self.weaponList[gunPos]) == gunClass:
            mainLogger.info(
                f"Player {self.name} try to buy weapon {gunType2name[gunType]} but failed due to same weapon, guntype = {gunType},gunPos = {gunPos}, {type(self.weaponList[gunPos])} == {type(gunClass)}")
            return

        mainLogger.info(f"Player {self.name} bought weapon {gunType2name[gunType]}")
        self.weaponList[gunPos] = gunClass(self)
        self.money -= moneyNeeded
        self.chooseWeapon(2)

    def tpSpawnpoint(self, n=None):
        if n:
            pass
        else:
            n = self.team - 1
        self.body.position = spawnpoints[n]

    def generate_weaponList(self):
        global weaponList
        if ROOM.state == 1:
            self.weaponList = [Weapon_machineGun(self, infiniteBullet=True), Weapon_rifle(self, infiniteBullet=True),
                               Weapon_sniper(self, infiniteBullet=True), Grenade_grenade(self), Grenade_fire(self)]
        else:
            self.weaponList = [None, Weapon_pistol(self), None, None, None] + [None]

    def checkChoice(self, weaponType):
        if 1 <= weaponType <= len(self.weaponList):
            if self.weaponList[weaponType - 1] != None:
                return True
        return False

    def chooseWeapon(self, weaponType):
        if self.checkChoice(weaponType):
            self.weapon = self.weaponList[weaponType - 1]
            self.weapon_choice = weaponType
            if 1 <= self.weapon_choice <= 3:
                self.lastMainWeapon = self.weapon_choice
            # mainLogger.info(f'Player {self.name} choose weapon: {weaponType} -> {self.weapon}')
        else:
            mainLogger.warning(f'Player {self.name} choose weapon: {weaponType}, Unavailable weapon!')
            self.weapon = self.weaponList[0]
            mainLogger.warning(f'Using the default weapon! weapon: {self.weaponList[0]}')

    def position(self) -> tuple:
        return self.body.position.int_tuple

    def killPlayer(self, p):
        p: Player
        self.money += 300
        self.killedCountTotal += 1
        self.killedList.append(Player_kill(self.name, p.name, tickcount, p.position()))
        if len(self.killedList) > 20:
            self.killedList.pop(0)
        self.lastKillMVPProcessed = False

    def MVPPlayer(self):  # No usage
        if self.lastKillMVPProcessed == False:
            self.lastKillMVPProcessed = True
            if len(self.killedList) >= self.mvp_killedPlayerNumber:
                lastnkilledTime = self.killedList[len(self.killedList) - 1 - self.mvp_killedPlayerNumber].killedTime

                if tickcount - lastnkilledTime < self.mvp_killedTime * fps:
                    self.killedList.clear()
                    return True
                return False
            return False
        return False

    def kill(self):
        self.hp = 0
        self.state = 0
        self.body.position = (-1000, -1000)
        self.head_pos = (-1000, -1000)
        try:
            self.space.remove(self.body, self.shape)
        except:
            pass

        # self.reborn()

    def checkReload(self):
        return self.weapon.bulletLeft > 0 and self.weapon.bulletNow < self.weapon.bulletConstant and not self.reloading

    def reload(self):
        self.reloading = True
        self.weapon.reload_cd = self.weapon.reload_constant

    def reborn(self):
        if self.state == 0:
            self.generate_weaponList()

        for w in self.weaponList:
            w.__init__(self)

        self.body.velocity = (0, 0)
        try:
            self.space.add(self.body, self.shape)
        except:
            pass
        self.state = 1
        self.character.reset()

        self.killedList.clear()
        self.changingGun = False
        self.changeGun_CD = 0
        self.reloading = False

        self.hp = 100
        self.reborn_defend_tick = self.reborn_defend_tick_constant
        self.tpSpawnpoint()
        self.chooseWeapon(2)

    def updateHead(self):
        angle = self.sandbox.state_angle
        self.head_pos = self.calHeadPos(angle)

    def calHeadPos(self, angle) -> tuple[int, int]:
        angle_r = math.radians(angle)
        d = self.radius
        center = self.position()
        pos = angleANDradius2pos(center, angle_r, d)
        return pos

    def beatBack(self):
        self.beatBackReset()

        radius = self.beatBack_speed
        angle_r = math.radians(self.beatBack_angle)
        x_velocity = math.cos(angle_r) * radius
        y_velocity = math.sin(angle_r) * radius
        force = Vec2d(x_velocity, y_velocity) * move_speed_increase_rate
        self.body.apply_force_at_world_point(force, self.body.position)

    def beatBackStart(self, angle):
        self.beatBack_angle = angle
        self.state = 2
        self.beatBack_tick = self.beatBack_tick_constant

    def beatBackReset(self):
        if self.reloading:
            self.reload()
        elif self.changingGun:
            self.changeGun_CD = self.weapon.changeGun_CD_constant
            self.changingGun = True


class Player_Sandbox:
    state_angle: int
    state_move_angle: int
    action_move: bool
    action_chooseWeapon: int
    action_reload: bool
    action_fire: bool
    action_shift: bool

    def __init__(self, p: Player):
        self.update(p)

    def update(self, p: Player):
        self.body = p.body
        self.hp = p.hp
        self.name = p.name
        self.angle = p.angle
        self.move_angle = p.move_angle
        self.reloading = p.reloading
        self.changeGun_CD = p.changeGun_CD
        self.changingGun = p.changingGun
        self.weapon_choice = p.weapon_choice
        self.move_speed = p.move_speed
        self.shift_tick = p.shift_tick
        self.shift_state = p.shift_state

        self.key_w = p.key_w
        self.key_a = p.key_a
        self.key_s = p.key_s
        self.key_d = p.key_d
        self.key_r = p.key_r
        self.key_f = p.key_f
        self.key_z = p.key_z
        self.key_m1 = p.key_m1
        self.key_1 = p.key_1
        self.key_2 = p.key_2
        self.key_3 = p.key_3
        self.key_4 = p.key_4
        self.key_5 = p.key_5

        self.radius = p.radius
        self.mass = p.mass
        self.moment = p.moment

        if p.weapon.type == 4 or p.weapon.type == 5:
            self.weapon = Grenade_Sandbox(p.weapon)
        else:
            self.weapon = Weapon_Sandbox(p.weapon)
        # self.weaponList = [Weapon_Sandbox(self, w) for w in p.weaponList]

        self.reset()

    def reset(self):
        self.state_angle = self.angle
        self.state_move_angle = self.move_angle
        self.action_move = False
        self.action_reload = False
        self.action_fire = False
        self.action_shift = False
        self.action_chooseWeapon = -1

    def position(self) -> tuple:
        return self.body.position.int_tuple

    def checkReload(self):
        return self.weapon.bulletLeft > 0 and self.weapon.bulletNow < self.weapon.bulletConstant and not self.reloading

    def chooseWeapon(self, weaponType):
        self.action_chooseWeapon = weaponType

    def reload(self):
        self.action_reload = True

    def fire(self):
        self.action_fire = True

    def move(self, angle):
        self.state_move_angle = angle


class Bullet:
    dead: bool
    by: str
    player: Player
    hp: int
    damage: int
    bullet_radius: int
    bullet_radius_collision: int
    bullet_mass: float
    bullet_speed: float
    bullet_body: pymunk.Body
    bullet_shape: pymunk.Circle

    def __init__(self, player: Player, bullet_radius: int, bullet_radius_collision: int, bullet_speed: int, hp: int):
        global bullets
        self.dead = False

        self.by = player.name
        self.player = player
        player_body = player.body
        player_angle = player.sandbox.state_angle

        self.hp = hp
        self.damage = hp

        self.bullet_radius = bullet_radius
        self.bullet_radius_collision = bullet_radius_collision

        self.bullet_mass = 0.1
        self.bullet_speed = bullet_speed * game_speed / space_tick

        self.bullet_body = pymunk.Body(self.bullet_mass,
                                       pymunk.moment_for_circle(self.bullet_mass, 0, self.bullet_radius))  # 使用合适的质量和惯性值
        self.bullet_body.position = player_body.position
        self.bullet_shape = pymunk.Circle(self.bullet_body, self.bullet_radius)

        spread_min, spread_max = self.player.weapon.spreadRange
        offset: int = self.player.weapon.spreadOffset
        spread_rate: float = self.player.body.velocity.length / move_speed_constant
        angle = player_angle

        if spread_rate < spread_min:
            angle = angle
        elif spread_min < spread_rate < spread_max:
            angle += random.randint(-offset, offset) * ((spread_rate - spread_min) / (spread_max - spread_min))
        else:
            angle += random.randint(-offset, offset)

        self.bullet_body.velocity = (self.bullet_speed * math.cos(math.radians(angle)),
                                     self.bullet_speed * math.sin(math.radians(angle)))

        self.fire()

    def fire(self):
        if self.player.character.type == 2:  # 飞雷神
            character: Character_YellowFlash = self.player.character
            if character.skill_state == 21:
                character.attach(self, self.bullet_body)

        bullets.append(self)

    def position(self):
        return self.bullet_body.position.int_tuple


class Bullet_Sandbox:
    def __init__(self, b: Bullet):
        p_sandbox = b.player.sandbox
        self.dead = b.dead
        self.by = b.by
        self.player = p_sandbox
        self.hp = b.hp
        self.bullet_radius = b.bullet_radius
        self.bullet_radius_collision = b.bullet_radius_collision
        self.bullet_mass = b.bullet_mass
        self.bullet_speed = b.bullet_speed
        self.bullet_body = pymunk.Body(self.bullet_mass,
                                       pymunk.moment_for_circle(self.bullet_mass, 0, self.bullet_radius))  # 使用合适的质量和惯性值
        self.bullet_body.position = b.bullet_body.position
        self.bullet_body.velocity = b.bullet_body.velocity
        self.bullet_shape = pymunk.Circle(self.bullet_body, self.bullet_radius)

    def position(self):
        return self.bullet_body.position.int_tuple


def SortBulletByX(bullet: Bullet):
    return bullet.position()[0]


class Bullet_machineGun(Bullet):
    def __init__(self, player: Player):
        self.bullet_radius = 7
        self.bullet_radius_collision = 7
        self.bullet_speed: int = 1200
        self.hp = 100
        Bullet.__init__(self, player, self.bullet_radius, self.bullet_radius_collision, self.bullet_speed, self.hp)


class Bullet_rifle(Bullet):
    def __init__(self, player: Player):
        self.bullet_radius = 10
        self.bullet_radius_collision = 10
        self.bullet_speed: int = 1400
        self.hp = 200
        Bullet.__init__(self, player, self.bullet_radius, self.bullet_radius_collision, self.bullet_speed, self.hp)


class Bullet_sniper(Bullet):
    def __init__(self, player: Player):
        self.bullet_radius = 15
        self.bullet_radius_collision = 15
        self.bullet_speed: int = 1600
        self.hp = 500
        Bullet.__init__(self, player, self.bullet_radius, self.bullet_radius_collision, self.bullet_speed, self.hp)


class Bullet_RPG(Bullet):
    def __init__(self, player: Player):
        self.bullet_radius = 30
        self.bullet_radius_collision = 30
        self.bullet_speed: int = 120
        self.hp = 1500
        Bullet.__init__(self, player, self.bullet_radius, self.bullet_radius_collision, self.bullet_speed, self.hp)


class Bullet_pistol(Bullet):
    def __init__(self, player: Player):
        self.bullet_radius = 5
        self.bullet_radius_collision = 5
        self.bullet_speed: int = 1400
        self.hp = 100
        Bullet.__init__(self, player, self.bullet_radius, self.bullet_radius_collision, self.bullet_speed, self.hp)


class Bullet_xm1014(Bullet):
    def __init__(self, player: Player):
        self.bullet_radius = 7
        self.bullet_radius_collision = 7
        self.bullet_speed: int = 1200
        self.hp = 100
        Bullet.__init__(self, player, self.bullet_radius, self.bullet_radius_collision, self.bullet_speed, self.hp)


class Weapon_Gun:
    shot_cd: int
    shot_cd_constant: int
    reload_cd: int  # tick
    reload_constant: int  # tick
    bulletNow: int
    bulletConstant: int
    bulletLeft: int
    player: Player
    bulletType: Bullet
    damage: int
    head_damage: int
    type: int
    changeGun_CD: int
    changeGun_CD_constant: int  # tick
    spreadRange: tuple
    spreadOffset: int

    def __init__(self, player: Player, bulletType: Union[Bullet_sniper, Bullet_rifle, Bullet_machineGun],
                 shot_cd_constant: int, bulletNow: int, bulletLeft: int, damage: int, head_damage: int, gunType: int,
                 changeGun_CD_constant: int, reload_constant: int, spreadRange: tuple, spreadOffset: int):
        self.shot_cd = 0
        self.shot_cd_constant = shot_cd_constant  # tick
        self.reload_constant = reload_constant  # (second * tick): tick
        self.reload_cd = 0
        self.bulletNow = bulletNow
        self.bulletConstant = self.bulletNow
        self.bulletLeft = bulletLeft
        self.player = player
        self.bulletType = bulletType
        self.damage = damage
        self.head_damage = head_damage
        self.type = gunType
        self.changeGun_CD = 0
        self.changeGun_CD_constant = changeGun_CD_constant  # tick
        self.spreadRange = spreadRange
        self.spreadOffset = spreadOffset

    def fire(self):
        self.shot_cd = self.shot_cd_constant
        self.bulletNow -= 1
        self.bulletType(self.player)


class Weapon_Sandbox:
    def __init__(self, w: Weapon_Gun):
        p_sandbox = w.player.sandbox
        self.shot_cd = w.shot_cd
        self.shot_cd_constant = w.shot_cd_constant
        self.reload_cd = w.reload_cd
        self.reload_constant = w.reload_constant
        self.bulletNow = w.bulletNow
        self.bulletConstant = w.bulletConstant
        self.bulletLeft = w.bulletLeft
        self.player = p_sandbox
        self.bulletType = w.bulletType
        self.damage = w.damage
        self.head_damage = w.head_damage
        self.type = w.type
        self.changeGun_CD = w.changeGun_CD
        self.changeGun_CD_constant = w.changeGun_CD_constant
        self.spreadRange = w.spreadRange
        self.spreadOffset = w.spreadOffset


class Weapon_machineGun(Weapon_Gun):
    money = 1200

    def __init__(self, player: Player, infiniteBullet=False):
        self.shot_cd_constant = int(1 / 12 * fps)  # 5
        self.bulletNow = 30
        if infiniteBullet:
            self.bulletNow = 9999
        self.bulletLeft = 180
        self.damage = 10
        self.head_damage = 110
        self.gunType = 1
        self.changeGun_CD_constant = int(0.5 * fps)
        self.reload_constant = int(1.5 * fps)
        self.spreadRange = (0.8, 0.9)
        self.spreadOffset = 15
        Weapon_Gun.__init__(self, player, Bullet_machineGun, self.shot_cd_constant, self.bulletNow, self.bulletLeft,
                            self.damage, self.head_damage, self.gunType, self.changeGun_CD_constant,
                            self.reload_constant,
                            self.spreadRange, self.spreadOffset)


class Weapon_rifle(Weapon_Gun):
    money = 2300

    def __init__(self, player: Player, infiniteBullet=False):
        self.shot_cd_constant = int(1 / 8 * fps)  # 7
        self.bulletNow = 15
        self.bulletLeft = 90
        if infiniteBullet:
            self.bulletNow = 9999
        # self.bulletLeft = 9999
        self.damage = 20
        self.head_damage = 150
        self.gunType = 2
        self.changeGun_CD_constant = int(0.5 * fps)
        self.reload_constant = int(2 * fps)
        self.spreadRange = (0.5, 0.7)
        self.spreadOffset = 20
        Weapon_Gun.__init__(self, player, Bullet_rifle, self.shot_cd_constant, self.bulletNow, self.bulletLeft,
                            self.damage, self.head_damage, self.gunType, self.changeGun_CD_constant,
                            self.reload_constant,
                            self.spreadRange, self.spreadOffset)


class Weapon_sniper(Weapon_Gun):
    money = 3500

    def __init__(self, player: Player, infiniteBullet=False):
        self.shot_cd_constant = int(1 * fps)
        self.bulletNow = 3
        self.bulletLeft = 18
        if infiniteBullet:
            self.bulletNow = 9999
        # self.bulletLeft = 9999
        self.damage = 100
        self.head_damage = 230
        self.gunType = 3
        self.changeGun_CD_constant = int(1 * fps)
        self.reload_constant = int(2 * fps)
        self.spreadRange = (0.4, 0.6)
        self.spreadOffset = 30
        Weapon_Gun.__init__(self, player, Bullet_sniper, self.shot_cd_constant, self.bulletNow, self.bulletLeft,
                            self.damage, self.head_damage, self.gunType, self.changeGun_CD_constant,
                            self.reload_constant,
                            self.spreadRange, self.spreadOffset)


class Weapon_RPG(Weapon_Gun):
    money = 1500

    def __init__(self, player: Player):
        self.shot_cd_constant = int(1 * fps)
        self.bulletNow = 1
        self.bulletLeft = 3
        # self.bulletLeft = 9999
        self.damage = 20
        self.head_damage = 230
        self.gunType = 6
        self.changeGun_CD_constant = int(1 * fps)
        self.reload_constant = int(3 * fps)
        self.spreadRange = (1, 1)
        self.spreadOffset = 0
        Weapon_Gun.__init__(self, player, Bullet_RPG, self.shot_cd_constant, self.bulletNow, self.bulletLeft,
                            self.damage, self.head_damage, self.gunType, self.changeGun_CD_constant,
                            self.reload_constant,
                            self.spreadRange, self.spreadOffset)


class Weapon_pistol(Weapon_Gun):
    money = 200

    def __init__(self, player: Player):
        self.shot_cd_constant = int(1 / 6 * fps)
        self.bulletNow = 12
        self.bulletLeft = 36
        # self.bulletLeft = 9999
        self.damage = 20
        self.head_damage = 70
        self.gunType = 7
        self.changeGun_CD_constant = int(0.3 * fps)
        self.reload_constant = int(1 * fps)
        self.spreadRange = (0.7, 1)
        self.spreadOffset = 5
        Weapon_Gun.__init__(self, player, Bullet_pistol, self.shot_cd_constant, self.bulletNow, self.bulletLeft,
                            self.damage, self.head_damage, self.gunType, self.changeGun_CD_constant,
                            self.reload_constant,
                            self.spreadRange, self.spreadOffset)


class Weapon_xm1014(Weapon_Gun):
    money = 2000

    def __init__(self, player: Player):
        self.shot_cd_constant = int(1 / 3 * fps)
        self.bulletNow = 6
        self.bulletLeft = 24
        # self.bulletLeft = 9999
        self.damage = 10
        self.head_damage = 70
        self.gunType = 8
        self.changeGun_CD_constant = int(0.7 * fps)
        self.reload_constant = int(3 * fps)
        self.spreadRange = (0, 0.5)
        self.spreadOffset = 20
        Weapon_Gun.__init__(self, player, Bullet_xm1014, self.shot_cd_constant, self.bulletNow, self.bulletLeft,
                            self.damage, self.head_damage, self.gunType, self.changeGun_CD_constant,
                            self.reload_constant,
                            self.spreadRange, self.spreadOffset)

        self.bulletperTime = 6

    def fire(self):
        self.shot_cd = self.shot_cd_constant
        self.bulletNow -= 1
        for i in range(self.bulletperTime):
            self.bulletType(self.player)


class Grenade:
    dead: bool
    shot_cd: int
    bulletNow: int
    bulletLeft: int
    reload_cd: int
    type: int
    changeGun_CD: int
    changeGun_CD_constant: int
    by: str
    player: Player
    grenade_radius: int
    grenade_mass: float
    grenade_speed: float

    grenade_body: pymunk.Body
    grenade_shape: pymunk.Circle

    damage: float
    damage_radius: float

    def __init__(self, player: Player, grenade_radius: int, grenade_speed: int, gunType: int, damage: float,
                 damage_radius: float):
        global bullets
        self.dead = False
        self.shot_cd = 0
        self.bulletNow = 1
        self.bulletLeft = 0
        self.reload_cd = 0
        self.type = gunType
        self.changeGun_CD = 0
        self.changeGun_CD_constant = int(0.5 * fps)

        self.damage = damage
        self.damage_radius = damage_radius

        self.by = player.name
        self.player = player

        self.grenade_radius = grenade_radius
        self.grenade_mass = 0.1
        self.grenade_speed = grenade_speed * game_speed / space_tick

        self.grenade_body = pymunk.Body(self.grenade_mass,
                                        pymunk.moment_for_circle(self.grenade_mass, 0,
                                                                 self.grenade_radius))  # 使用合适的质量和惯性值

        self.grenade_shape = pymunk.Circle(self.grenade_body, self.grenade_radius)
        self.grenade_shape.filter = self.player.filter
        self.grenade_shape.elasticity = 1

    def fire(self):
        global space

        self.grenade_body.position = self.player.body.position
        self.grenade_body.velocity = (self.grenade_speed * math.cos(math.radians(self.player.angle)),
                                      self.grenade_speed * math.sin(math.radians(self.player.angle)))
        self.grenade_body.velocity += self.player.body.velocity

        self.bulletNow = 0
        self.player.chooseWeapon(self.player.lastMainWeapon)
        self.player.changeGun_CD = self.player.weapon.changeGun_CD_constant
        self.player.changingGun = True

        if self.player.character.type == 2:  # 飞雷神
            character: Character_YellowFlash = self.player.character
            if character.skill_state == 21:
                character.attach(self, self.grenade_body)
        space.add(self.grenade_body, self.grenade_shape)

        grenades.append(self)

    def update(self):
        pass

    def position(self):
        return self.grenade_body.position.int_tuple


class Grenade_Sandbox:
    def __init__(self, g: Grenade):
        p_sandbox = g.player.sandbox
        self.dead = g.dead
        self.shot_cd = g.shot_cd
        self.bulletNow = g.bulletNow
        self.bulletLeft = g.bulletLeft
        self.reload_cd = g.reload_cd
        self.type = g.type
        self.changeGun_CD = g.changeGun_CD
        self.changeGun_CD_constant = g.changeGun_CD_constant
        self.by = g.by
        self.player = p_sandbox
        self.grenade_radius = g.grenade_radius
        self.grenade_mass = g.grenade_mass
        self.grenade_speed = g.grenade_speed

        self.grenade_body = g.grenade_body
        self.grenade_shape = g.grenade_shape

        self.damage = g.damage
        self.damage_radius = g.damage_radius

    def position(self):
        return self.grenade_body.position.int_tuple


class Grenade_grenade(Grenade):
    money = 500

    def __init__(self, player: Player):
        self.grenade_radius = 5
        self.grenade_speed: int = 800
        self.gunType = 4
        self.damage = 50
        self.damage_radius = 200
        Grenade.__init__(self, player, self.grenade_radius, self.grenade_speed, self.gunType, self.damage,
                         self.damage_radius)

        self.cd = 1 * fps

    def fire(self):
        Grenade.fire(self)
        self.player.weaponList[3] = None

    def update(self):
        if self.cd > 0:
            self.cd -= 1
        else:
            self.explode()

    def explode(self):
        global Players, space
        for currentPlayer in Players.values():
            currentPlayer: Player

            if collide_circle(self.position(), self.damage_radius, currentPlayer.position(),
                              currentPlayer.radius):
                damage = self.damage

                if currentPlayer.reborn_defend_tick > 0:
                    continue

                if currentPlayer.character.type == 3:
                    character: Character_RedMoonObito = currentPlayer.character
                    if character.fade:
                        continue

                if currentPlayer.team == self.player.team:
                    damage /= 2

                if currentPlayer.hp - damage > 0:
                    currentPlayer.hp -= damage
                else:
                    currentPlayer.kill()
                    self.player.killPlayer(currentPlayer)

        self.dead = True
        space.remove(self.grenade_body, self.grenade_shape)


class Grenade_fire(Grenade):
    money = 400

    def __init__(self, player: Player):
        self.grenade_radius = 1
        self.grenade_speed: int = 0
        self.gunType = 5

        self.damage = 0
        self.damage_radius = 0
        self.player_velocity = False

        Grenade.__init__(self, player, self.grenade_radius, self.grenade_speed, self.gunType, self.damage,
                         self.damage_radius)

        self.fall_cd = 1 * fps
        self.fall_cd_constant = 1 * fps
        self.last_cd = 8 * fps
        self.last_cd_constant = 8 * fps

        self.damaging = False
        self.spreadTime = 2  # 秒
        self.damage_max = 8  # 总共4秒完成伤害扩散
        self.damage_radius_max = 150  # 总共4秒完成范围扩散

        # 15 tick 结算一次, 最小伤害1，最大8
        self.damage_increasePer15Tick = (self.damage_max / self.spreadTime) / (60 / 15)
        self.damage_radius_increasePer15Tick = (self.damage_radius_max / self.spreadTime) / (60 / 15)

        self.landing_height = 100
        self.target_pos = Vec2d(0, 0)

    def fire(self):
        global space
        self.target_pos = self.player.mouse_pos

        self.grenade_body.position = self.target_pos
        self.grenade_body.velocity = (self.grenade_speed * math.cos(math.radians(self.player.angle)),
                                      self.grenade_speed * math.sin(math.radians(self.player.angle)))

        self.bulletNow = 0
        self.player.chooseWeapon(self.player.lastMainWeapon)
        self.player.changeGun_CD = self.player.weapon.changeGun_CD_constant
        self.player.changingGun = True
        self.player.weaponList[self.type - 1] = None

        space.add(self.grenade_body, self.grenade_shape)
        grenades.append(self)
        self.player.weaponList[4] = None

    def update(self):
        if self.fall_cd > 0:
            self.fall_cd -= 1

            self.grenade_body.position = Vec2d(self.target_pos.x, self.target_pos.y - self.landing_height * (
                    self.fall_cd / self.fall_cd_constant))

        else:
            self.fall_cd = 0
            self.damaging = True
            self.grenade_body.position = self.target_pos

            if self.last_cd > 0:
                self.last_cd -= 1

                if tickcount % 15 == 0:
                    self.damage += self.damage_increasePer15Tick
                    if self.damage > self.damage_max:
                        self.damage = self.damage_max

                    self.damage_radius += self.damage_radius_increasePer15Tick
                    if self.damage_radius > self.damage_radius_max:
                        self.damage_radius = self.damage_radius_max

                    for currentPlayer in Players.values():
                        currentPlayer: Player

                        if collide_circle(self.position(), self.damage_radius, currentPlayer.position(),
                                          currentPlayer.radius):
                            damage = self.damage

                            if currentPlayer.reborn_defend_tick > 0:
                                continue

                            if currentPlayer.character.type == 3:
                                character: Character_RedMoonObito = currentPlayer.character
                                if character.fade:
                                    continue

                            if currentPlayer.team == self.player.team:
                                damage /= 2

                            if currentPlayer.hp - damage > 0:
                                currentPlayer.hp -= damage
                            else:
                                currentPlayer.kill()
                                self.player.killPlayer(currentPlayer)

            else:
                self.damaging = False
                self.last_cd = 0
                self.dead = True


class Kunai:
    barrier_offset = 10
    speed = 3500
    max_distance = 200
    tp_damage_radius = 80

    def __init__(self, player: Player, mode=1):
        self.mode = mode  # 1: 形态1，2：形态2，没有距离上限
        self.stop = False

        self.by = player.name
        self.player = player
        player_body = player.body
        player_angle = player.sandbox.state_angle

        self.bullet_mass = 1
        self.bullet_radius = 5
        self.bullet_speed = self.speed * game_speed / space_tick

        self.bullet_body = pymunk.Body(self.bullet_mass,
                                       pymunk.moment_for_circle(self.bullet_mass, 0, self.bullet_radius))  # 使用合适的质量和惯性值
        self.bullet_body.position = player_body.position
        self.bullet_shape = pymunk.Circle(self.bullet_body, self.bullet_radius)

        self.bullet_body.velocity = (self.bullet_speed * math.cos(math.radians(player_angle)),
                                     self.bullet_speed * math.sin(math.radians(player_angle)))

        self.start_pos = self.bullet_body.position

        self.fire()

    def fire(self):
        mainLogger.info("sound")
        awaitingMessage.append(json.dumps({"type": "sound", "name": "kunai"}))
        kunais.append(self)

    def stopMoving(self):
        self.stop = True
        self.bullet_body.velocity = (0, 0)

    def update(self):
        if self.mode == 1 and self.start_pos.get_distance(self.bullet_body.position) > self.max_distance:
            self.stopMoving()

    def position(self):
        return self.bullet_body.position.int_tuple

    def tp(self, pos=None):
        if pos == None:
            self.player.body.position = self.bullet_body.position
        else:
            self.player.body.position = pos

        awaitingMessage.append(json.dumps({"type": "sound", "name": "kunai"}))

        for currentPlayer in Players.values():
            currentPlayer: Player

            if currentPlayer == self.player:
                continue

            if collide_circle(self.bullet_body.position.int_tuple, self.tp_damage_radius, currentPlayer.position(),
                              currentPlayer.radius):

                if currentPlayer.reborn_defend_tick > 0:
                    continue

                if currentPlayer.character.type == 3:
                    character: Character_RedMoonObito = currentPlayer.character
                    if character.fade:
                        continue

                angle = calculate_angle(self.bullet_body.position.int_tuple, currentPlayer.position())
                currentPlayer.beatBackStart(angle)

        self.destroy()

    def destroy(self):
        character: Character_YellowFlash = self.player.character
        character.kunai = None
        kunais.remove(self)


class Character:
    code2characterName = {0: "default", 1: "时间转移", 2: "飞雷神", 3: "红夜带土"}
    type = 0

    def __init__(self, p: Player):
        self.player = p

    def update(self):
        pass

    def reset(self):
        pass


class Character_TimeTransferor(Character):
    def __init__(self, p: Player):
        Character.__init__(self, p)
        self.type = 1

    def update(self):
        player = self.player
        sandbox: Player_Sandbox = self.player.sandbox
        weapon: Weapon_Gun = self.player.weapon
        if player.key_f or (player.key_m1 and weapon.bulletNow > 0 and not player.changingGun and not player.reloading):
            sandbox.action_shift = False
        else:
            sandbox.action_shift = True


class Character_YellowFlash(Character):  # 黄色闪光飞雷神水门
    kunai: Union[None, Kunai]
    attachment: Union[None, Bullet, Grenade]
    attachment_body: Union[None, pymunk.Body]

    def __init__(self, p: Player):
        Character.__init__(self, p)
        self.type = 2

        self.kunai = None
        self.attachment = None
        self.attachment_body = None

        self.skill_state = 11
        # ab 形式 a代表形态(1/2) b代表状态 {10: 形态1冷却, 11:形态1未使用, 12:形态1插标，13:形态1传送, 20:形态2冷却,21:形态2未使用,22:形态2插标,23:形态2传送}

        self.cd = 0  # 冷却时间
        self.Mode1_maintainTime = 0
        self.Mode1_maintainTime_constant = int(10 * fps)
        self.cd_mode1_constant = int(5 * fps)
        self.cd_mode2_constant = int(5 * fps)  # 固定冷却时间

        self.on = False  # On/Off
        self.lastKey = False  # 最后的按键

        self.on_switch = False
        self.lastKey_switch = False

    def getInCD(self, mode):
        if self.kunai:
            self.kunai.destroy()
        if mode == 1:
            self.cd = self.cd_mode1_constant
            self.skill_state = 10
        elif mode == 2:
            self.cd = self.cd_mode2_constant
            self.skill_state = 20
        else:
            mainLogger.error(
                f"ERROR mode when getInCD YellowFlash: {self}, player: {self.player}, name: {self.player.name}")

    def reset(self):
        if self.kunai:
            self.kunai.destroy()
        self.attachment = None
        self.attachment_body = None
        if str(self.skill_state)[0] == "1":  # 形态1
            self.skill_state = 11
        elif str(self.skill_state)[0] == "2":  # 形态2
            self.skill_state = 21
        else:
            mainLogger.error(
                f"Wrong skill_state to reset! skill_state: {self.skill_state}, player name: {self.player.name}")
        self.cd = 0
        self.Mode1_maintainTime = 0

    def switch(self):
        if self.skill_state == 11:
            self.skill_state = 21
        elif self.skill_state == 21:
            self.skill_state = 11

    def attach(self, attachment, body: pymunk.Body):
        self.kunai = Kunai(self.player, mode=2)
        self.attachment = attachment
        self.attachment_body = body
        self.skill_state = 22

    def update(self):
        player = self.player
        if self.on:
            self.on = False
        if not self.lastKey and player.key_f:
            self.on = True
        self.lastKey = player.key_f

        if self.on_switch:
            self.on_switch = False
        if not self.lastKey_switch and player.key_z:
            self.on_switch = True
        self.lastKey_switch = player.key_z

        if self.on_switch:
            self.switch()

        if self.on and self.skill_state == 11:
            self.kunai = Kunai(self.player)
            self.skill_state = 12
            self.Mode1_maintainTime = self.Mode1_maintainTime_constant
        elif self.on and self.skill_state == 12:
            self.kunai.tp()
            self.getInCD(1)

        if self.on and self.skill_state == 22:
            self.kunai.tp(self.attachment.position())
            self.getInCD(2)

        if self.skill_state == 12 and self.Mode1_maintainTime > 0:
            self.Mode1_maintainTime -= 1

        if self.skill_state == 12 and self.Mode1_maintainTime <= 0:
            self.getInCD(1)

        if self.skill_state == 22 and (self.attachment == None or self.attachment.dead):
            self.getInCD(2)

        if self.skill_state == 10 or self.skill_state == 20:
            if self.cd > 0:
                self.cd -= 1
            else:
                if self.skill_state == 10:
                    self.skill_state = 11
                elif self.skill_state == 20:
                    self.skill_state = 21


class Character_RedMoonObito(Character):  # 红夜带土
    radius = 100

    def __init__(self, p: Player):
        Character.__init__(self, p)
        self.type = 3

        self.fade = False  # 虚化状态
        self.fade_time = 0  # 虚化剩余时间
        self.fade_time_constant = 0  # 虚化总共时间
        self.skill_state = 0  # 技能状态 {-1: 冷却, 0: 未触发, 1: 一段, 2: 二段, 3: 三段} 目前没有三段
        self.cd = 0  # 冷却时间
        self.cd_constant = int(5 * fps)  # 固定冷却时间
        self.switch_time = 0  # 技能切换时间 （比如一段 --进入-> 二段，这个为触发下一段的时间*详情看更新日志）
        self.switch_time_constant = 0  # 技能切换总共时间

        self.on = False  # On/Off
        self.lastKey = False  # 最后的按键

    def getInCD(self):
        self.fade = False
        self.fade_time = 0
        self.skill_state = -1
        self.cd = self.cd_constant
        self.switch_time = 0

    def reset(self):
        self.fade = False  # 虚化状态
        self.fade_time = 0  # 虚化剩余时间
        self.skill_state = 0  # 技能状态 {-1: 冷却, 0: 未触发, 1: 一段, 2: 二段, 3: 三段} 目前没有三段
        self.cd = 0  # 冷却时间
        self.switch_time = 0  # 技能切换时间 （比如一段 --进入-> 二段，这个为触发下一段的时间*详情看更新日志）

    def reduceHP(self, damage=10):
        damage = 0  # 虚化不掉血
        if self.player.hp > damage:
            self.player.hp -= damage
            return True
        return False

    def update(self):
        if self.player.reborn_defend_tick > 0:
            return

        player = self.player

        if self.on:
            self.on = False

        if not self.lastKey and player.key_f:
            self.on = True
        self.lastKey = player.key_f

        if self.skill_state == -1:
            if self.cd > 0:
                self.cd -= 1
            else:
                self.skill_state = 0

        elif self.skill_state == 0:
            if self.on and self.reduceHP():
                self.skill_state = 1
                self.fade_time = int(0.5 * fps)  # 0.5秒
                self.fade_time_constant = int(0.5 * fps)  # 0.5秒
                self.switch_time = int(1.5 * fps)  # 1.5秒
                self.switch_time_constant = int(1.5 * fps)  # 1.5秒

        elif self.skill_state == 1:
            if self.on and self.switch_time > 0 and self.reduceHP():
                self.skill_state = 2
                self.fade_time = int(1 * fps)
                self.fade_time_constant = int(1 * fps)
                self.switch_time = int(2 * fps)
                self.switch_time_constant = int(2 * fps)
        elif self.skill_state == 2:
            if self.on and self.switch_time > 0 and self.reduceHP():
                self.skill_state = 3
                self.fade_time = int(1 * fps)
                self.fade_time_constant = int(1 * fps)
                self.switch_time = 0

        elif self.skill_state == 3:
            if self.fade_time == self.fade_time_constant // 2:  # 位移
                radius = 100
                angle_r = math.radians(self.player.move_angle)
                target_x, target_y = angleANDradius2pos(self.player.position(), angle_r, radius)
                while not (0 < target_x < width and 0 < target_y < height):
                    radius -= 1
                    target_x, target_y = angleANDradius2pos(self.player.position(), angle_r, radius)
                self.player.body.position = Vec2d(target_x, target_y)

            pass  # 等fade_time和switch_time在后面结算，然后进入冷却

        if self.fade_time > 0:
            self.fade = True
            self.fade_time -= 1
        else:
            self.fade = False

        if self.switch_time > 0:
            self.switch_time -= 1

        if not self.fade and self.switch_time <= 0 and not (self.skill_state == 0 or self.skill_state == -1):
            self.getInCD()


def isTheRoundEnd():
    teams = {}
    for currentPlayer in Players.values():
        team = currentPlayer.team

        if team not in teams:
            teams[team] = 0

        if currentPlayer.state != 0:
            teams[team] += 1

    if 0 in teams.values():
        winning_team = 0
        for t in teams:
            if teams[t] > 0:
                winning_team = t
        return True, winning_team
    return False, 0


with open('map.txt', 'r', encoding='utf-8') as f:
    map_info: str = f.read()

map_info: dict = json.loads(map_info)
map_width, map_height = map_info["size"]

# 设置窗口和物理空间
width, height = map_width, map_height

space = pymunk.Space()
space.gravity = (0, 0)  # 将重力设置为0
map_elasticity = 0.5

# 创建边界
barriers = [[(0, height), (width, height)], [(0, 0), (width, 0)], [(0, 0), (0, height)], [(width, 0), (width, height)]]
for i in barriers:
    ground = pymunk.Segment(space.static_body, i[0], i[1], 0)
    ground.filter = pymunk.ShapeFilter(group=1)  # map filter = 1
    ground.elasticity = map_elasticity
    space.add(ground)

game_speed = 1
fps = 60
space_tick = 5
tickcount = 0

move_speed_constant = 200 * game_speed / space_tick
move_speed_increase_rate = 10
move_speed_increase_rate_shift_release = move_speed_increase_rate * move_speed_increase_rate
ground_friction_rate = 0.15

bullets = []
bullets_message = []
bullets_sandbox = []

grenades = []
grenades_message = []
grenades_sandbox = []

kunais = []
kunais_message = []

connected_clients = {}
Players = {}
Players_sandbox = {}

awaitingMessage = []

timecostTotal = 0

# 1 for map
collision_handle_index = 2

map_image = pygame.Surface(size=(map_width, map_height))
map_image.fill((255, 255, 255))

files = getFileNames()

weaponList = [Weapon_machineGun, Weapon_rifle, Weapon_sniper, Weapon_RPG, Weapon_pistol, Weapon_xm1014]

extra_timesleep = 0

ROOM = Room()

gunType2class = {1: Weapon_machineGun, 2: Weapon_rifle, 3: Weapon_sniper, 4: Grenade_grenade, 5: Grenade_fire,
                 6: Weapon_RPG, 7: Weapon_pistol, 8: Weapon_xm1014}


def CreateMap():
    global map_image, map_info, spawnpoints

    spawnpoints = map_info["spawnpoint"]
    mainLogger.info(f"Spawnpoints: {spawnpoints}")

    # 创建地图碰撞体
    for element in map_info["circle"]:
        element: list

        # 创建一个静态的圆形 Body
        position: tuple = element[0]
        radius: int = element[1]

        moment = pymunk.moment_for_circle(mass=1, inner_radius=0, outer_radius=radius)
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        body.position = position  # 设置圆心位置
        shape = pymunk.Circle(body, radius)
        shape.elasticity = map_elasticity
        space.add(body, shape)

        pygame.draw.circle(map_image, (0, 0, 0), center=position, radius=radius)
    for element in map_info["poly"]:
        # 定义多边形的顶点坐标
        vertices: list = element

        # 创建多边形的Body
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        # 创建多边形形状
        polygon = pymunk.Poly(body, vertices)
        polygon.elasticity = map_elasticity
        # 添加多边形到空间
        space.add(body, polygon)
        pygame.draw.polygon(map_image, (0, 0, 0), polygon.get_vertices())

    mainLogger.info("Create Map Success")


def NewCollisionHandle():
    global collision_handle_index, space

    index = collision_handle_index
    handler = space.add_collision_handler(index, index)
    handler.pre_solve = lambda: False

    collision_handle_index += 1

    return pymunk.ShapeFilter(group=collision_handle_index - 1)


async def broadcast_message(message):
    for client in connected_clients.values():
        asyncio.create_task(client.send(message))


class CustomError(Exception):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details


async def handle_client(websocket: websockets.WebSocketClientProtocol, path):
    global connected_clients, Players
    addr = websocket.remote_address
    connected_clients[addr] = websocket

    try:
        await websocket.send(json.dumps({"type": "map", "map": map_info}))
        await websocket.send(json.dumps({"type": "config", "config": files}))

        data = await websocket.recv()
        data = json.loads(data)

        if data['type'] == 'join':
            name = data['name']
            config = data['config']
            team = data['team']
            MVPCode = data['MVPCode']
            character = data['character']
            if 1 <= MVPCode <= 19:
                pass
            else:
                raise CustomError(f"MVPCode not in range! MVPCode: {MVPCode}")

            p = Player(name, team, MVPCode)
            p.sandbox = Player_Sandbox(p)
            if team == 1:
                p.team = 1
            elif team == 2:
                p.team = 2
            else:
                raise CustomError(f"Wrong team! team:{team}")

            if character == 1:
                p.character = Character_TimeTransferor(p)
            elif character == 2:
                p.character = Character_YellowFlash(p)
            elif character == 3:
                p.character = Character_RedMoonObito(p)
            else:
                raise CustomError(f"Wrong character! character:{character}")

            Players[name] = p
            mainLogger.info(f"Player {name} join in with config {config}, from {addr}")

            if f"{config}.py" in files:
                cacheConfigName = generateLibCache(config)
                exec(f"import cache.config.{cacheConfigName} as {cacheConfigName}")
                exec(f"Players[name].lib = {cacheConfigName}")
                mainLogger.info(f"Existing config: {config}")
                mainLogger.info(f"imported {config}.py as {cacheConfigName}")
                mainLogger.info(f"Players['{name}'].lib = {cacheConfigName}")
            else:
                mainLogger.info(f"No file named {config}.py, using default")

        currentPlayer: Player = Players[name]

        while True:
            data = await websocket.recv()
            data = data.split('|')
            if len(data) == 2:  # Buy / emoji
                if data[0] == "buy":
                    item = int(data[1])
                    currentPlayer.buy(item)
                if data[0] == "emoji":
                    item = int(data[1])
                    currentPlayer.startEmoji(item)

            elif len(data) == 3:  # Keys

                keys = [i == "1" for i in data[0]]
                currentPlayer.key_w, currentPlayer.key_a, currentPlayer.key_s, currentPlayer.key_d, \
                currentPlayer.key_r, currentPlayer.key_f, currentPlayer.key_z, currentPlayer.key_m1, \
                currentPlayer.key_1, currentPlayer.key_2, currentPlayer.key_3, currentPlayer.key_4, currentPlayer.key_5 = keys

                mouse_pos = ast.literal_eval(data[1])
                currentPlayer.mouse_pos = Vec2d(mouse_pos[0], mouse_pos[1])
                angle_h = math.atan2(currentPlayer.mouse_pos.y, currentPlayer.mouse_pos.x)
                angle = math.degrees(angle_h)
                angle = calculate_angle(currentPlayer.position(), currentPlayer.mouse_pos.int_tuple)
                currentPlayer.angle = angle
                currentPlayer.move_angle = int(data[2])
            else:
                mainLogger.error(f"ERROR DATA from {name}!: f{data}")
                raise CustomError(f"ERROR DATA from {name}!: f{data}")

    except websockets.exceptions.ConnectionClosedError:
        mainLogger.info(f"Connection closed for {addr}")
    except Exception as e:
        error_info = traceback.format_exc()
        mainLogger.warning(f"ERROR occur when handle_client: {e}\nDetailed info:\n{error_info}")
    finally:
        if addr in connected_clients:
            del connected_clients[addr]
        if name in Players:
            Players[name].invalid = True
            del Players[name]
        await websocket.close()


async def main(port):
    # 同时运行WebSocket服务器和Judge函数
    server = await websockets.serve(handle_client, "0.0.0.0", port)

    judge_task = asyncio.create_task(Judge())

    # 等待服务器关闭和Judge函数完成
    await asyncio.gather(server.wait_closed(), judge_task)


async def Judge():
    global tickcount, bullets, Players, bullets_message, grenades_message, grenades, Players_sandbox, bullets_sandbox, grenades_sandbox
    global ERRORTIMES_JUDGE, kunais, kunais_message, extra_timesleep

    CreateMap()

    # 主循环
    running = True

    while running:

        try:
            os.system('clear')
            timeLogger.clear()

            timeLogger.addPoint("timecost_total")
            tickcount += 1

            ROOM.update()
            if len(Players) < 2:
                ROOM.warmup()

            roundEnd, winningTeam = isTheRoundEnd()
            if roundEnd and ROOM.state != 4:
                ROOM.roundEnd(winningTeam)

            timeLogger.addPoint("timecost_player")

            # 放在行动前，防止在后面的玩家获取前面玩家update过的信息
            Players_sandbox = {}
            for player in Players.values():
                player: Player
                Players_sandbox[player.name] = copy.deepcopy(player.sandbox)

            for currentPlayer in Players.values():
                currentPlayer: Player

                timeLogger.addPoint(f"{currentPlayer.name}_sandbox")

                if currentPlayer.sandbox == None:
                    currentPlayer.sandbox = Player_Sandbox(currentPlayer)

                currentPlayer_sandbox: Player_Sandbox = currentPlayer.sandbox
                currentPlayer_sandbox.update(currentPlayer)

                timeLogger.endPoint(f"{currentPlayer.name}_sandbox")

                timeLogger.addPoint(f"{currentPlayer.name}_update")

                map_sandbox = None  # map_image_sandbox(map_image)

                currentPlayer.logger.userio.switch()
                try:
                    currentPlayer_sandbox = currentPlayer.lib.update(currentPlayer_sandbox,
                                                                     copy.deepcopy(Players_sandbox), bullets_sandbox,
                                                                     grenades_sandbox, map_sandbox)
                except Exception as e:
                    error_info = traceback.format_exc()
                    mainLogger.error(
                        f"ERROR occurs when updating {currentPlayer.name}, reason: {e}\nDetailed info:\n{error_info}")
                    currentPlayer.logger.userio.write(
                        f"ERROR occurs when updating {currentPlayer.name}, reason: {e}\nDetailed info:\n{error_info}")

                currentPlayer.logger.update()
                currentPlayer.logger.userio.recover()

                timeLogger.endPoint(f"{currentPlayer.name}_update")

                '''
                if currentPlayer.MVPPlayer():
                    message = {"type": "mvp", "name": currentPlayer.name, "code": currentPlayer.MVPCode}
                    await broadcast_message(json.dumps(message))
                '''

                if currentPlayer.state == 2 and currentPlayer.beatBack_tick > 0:
                    currentPlayer.beatBack()
                    currentPlayer.beatBack_tick -= 1
                elif currentPlayer.state == 2 and currentPlayer.beatBack_tick == 0:
                    currentPlayer.state = 1

                if currentPlayer.state == 1:
                    currentPlayer.character.update()

                currentPlayer.shift_state = "normal"
                shift_times = 1

                if currentPlayer.character.type == 1:  # 时间转移者
                    if currentPlayer_sandbox.action_shift:
                        if currentPlayer.shift_tick + 1 <= currentPlayer.shift_tick_max:
                            currentPlayer.shift_state = "charging"
                            currentPlayer.body.velocity = (0, 0)
                            currentPlayer.shift_tick += 1
                    else:
                        if currentPlayer.shift_tick > 1:
                            currentPlayer.shift_state = "releasing"

                    if currentPlayer.shift_state == "charging":
                        shift_times = 0
                    elif currentPlayer.shift_state == "normal":
                        shift_times = 1
                    elif currentPlayer.shift_state == "releasing":
                        shift_times = currentPlayer.shift_tick
                    else:
                        mainLogger.error(
                            f"Player {currentPlayer.name} has wrong shift_state: {currentPlayer.shift_state}")

                if currentPlayer.state != 1 or ROOM.state == 2:
                    shift_times = 0

                currentPlayer.updateEmoji()

                for shift_tick_now in range(shift_times, 0, -1):
                    if not currentPlayer.changingGun:
                        # 开火
                        if currentPlayer_sandbox.action_fire:
                            if not currentPlayer.reloading:
                                if currentPlayer.weapon.shot_cd == 0 and currentPlayer.weapon.bulletNow > 0:
                                    currentPlayer.weapon.fire()
                                    if currentPlayer.character.type == 3 and currentPlayer.character.fade_time > 1: # 带土
                                        currentPlayer.character.fade_time = 1

                        # 主动换弹
                        if currentPlayer_sandbox.action_reload:
                            if currentPlayer.checkReload():
                                currentPlayer.reload()

                        # 处理换弹过程
                        if currentPlayer.reloading:
                            if currentPlayer.weapon.reload_cd > 0:
                                currentPlayer.weapon.reload_cd -= 1
                            else:
                                # 换弹完成
                                currentPlayer.weapon.reload_cd = 0
                                currentPlayer.reloading = False
                                changeBullet: int = min(currentPlayer.weapon.bulletLeft,
                                                        currentPlayer.weapon.bulletConstant - currentPlayer.weapon.bulletNow)
                                currentPlayer.weapon.bulletNow += changeBullet
                                currentPlayer.weapon.bulletLeft -= changeBullet

                    # 切枪
                    if currentPlayer_sandbox.action_chooseWeapon != -1:
                        choice = currentPlayer_sandbox.action_chooseWeapon

                        if choice != currentPlayer.weapon_choice and currentPlayer.checkChoice(choice):
                            if currentPlayer.reloading:
                                currentPlayer.weapon.reload_cd = 0
                                currentPlayer.reloading = False

                            currentPlayer.chooseWeapon(choice)
                            currentPlayer.changeGun_CD = currentPlayer.weapon.changeGun_CD_constant
                            currentPlayer.changingGun = True

                    # 处理切枪过程
                    if currentPlayer.changingGun:
                        if currentPlayer.changeGun_CD > 0:
                            currentPlayer.changeGun_CD -= 1
                        else:
                            # 切枪完成
                            currentPlayer.changeGun_CD = 0
                            currentPlayer.changingGun = False

                    # 处理开火间隔
                    if currentPlayer.weapon.shot_cd > 0:
                        currentPlayer.weapon.shot_cd -= 1

                    # 处理复活后金身时间
                    if currentPlayer.reborn_defend_tick > 0:
                        currentPlayer.reborn_defend_tick -= 1

                    flag_velocity_0 = False
                    if currentPlayer.character.type == 3:
                        if currentPlayer.character.skill_state == 3 and currentPlayer.character.fade_time > currentPlayer.character.fade_time_constant // 2:
                            flag_velocity_0 = True

                    # 移动加速度
                    if currentPlayer_sandbox.action_move:
                        radius = move_speed_constant
                        angle_r = math.radians(currentPlayer_sandbox.state_move_angle)
                        x_velocity = math.cos(angle_r) * radius
                        y_velocity = math.sin(angle_r) * radius
                        if currentPlayer.shift_state == "releasing":
                            force = Vec2d(x_velocity, y_velocity) * move_speed_increase_rate_shift_release
                        else:
                            force = Vec2d(x_velocity, y_velocity) * move_speed_increase_rate

                        if flag_velocity_0:
                            currentPlayer.body.velocity = (0, 0)
                        else:
                            currentPlayer.body.apply_force_at_world_point(force,
                                                                          currentPlayer.body.position)

                    if currentPlayer.shift_state == "releasing":
                        pass
                    else:
                        currentPlayer.body.velocity -= currentPlayer.body.velocity * ground_friction_rate

                    if currentPlayer.body.velocity.length > move_speed_constant:
                        if currentPlayer.shift_state == "releasing":
                            pass
                        else:
                            currentPlayer.body.velocity *= move_speed_constant / currentPlayer.body.velocity.length

                if currentPlayer.shift_state == "releasing":
                    currentPlayer.shift_tick = 1

            timeLogger.endPoint("timecost_player")

            timeLogger.addPoint("timecost_physics")

            # 更新物理空间
            for current_spacetick in range(space_tick):  # 看似客户端的gap很大，其实每个gap之间都有space_tick次判定，精度很高
                dt = 1.0 / fps
                # 这里才实际处理的玩家的移动
                space.step(dt)
                for currentPlayer in Players.values():
                    if currentPlayer.state != 0 and not currentPlayer.shift_state == "charging":
                        currentPlayer.updateHead()

                # 更新子弹
                new_bullets = []
                new_bullets_message = []
                new_bullets_sandbox = []

                bullets.sort(key=SortBulletByX)
                # print(bullets)
                index = -1
                for bullet in bullets:
                    bullet: Bullet
                    index += 1

                    if bullet.dead:
                        continue

                    bullet_body = bullet.bullet_body
                    bullet_shape = bullet.bullet_shape

                    # 子弹移动
                    bullet_body.position += bullet_body.velocity * (1.0 / fps)

                    # 玩家碰撞
                    collide_player = []
                    collide_head_player = []
                    for currentPlayer in Players.values():
                        currentPlayer: Player

                        # 自己发射的子弹不判定
                        if currentPlayer.name == bullet.player.name:
                            continue

                        if currentPlayer.character.type == 3:
                            character: Character_RedMoonObito = currentPlayer.character
                            if character.fade:
                                continue

                        # 先判定头部
                        if collide_circle(bullet_body.position, bullet.bullet_radius, currentPlayer.head_pos,
                                          currentPlayer.head_radius):
                            bullet.dead = True
                            collide_head_player.append(currentPlayer)
                        elif collide_circle(bullet_body.position, bullet.bullet_radius, currentPlayer.position(),
                                            currentPlayer.radius):
                            bullet.dead = True
                            collide_player.append(currentPlayer)

                    if collide_player:
                        # print(collide_player)
                        for currentPlayer in collide_player:
                            currentPlayer: Player
                            by = bullet.by
                            damage = Players[by].weapon.damage

                            if currentPlayer.reborn_defend_tick > 0:
                                damage = 0

                            if currentPlayer.team == bullet.player.team:
                                damage /= 2

                            if currentPlayer.hp - damage > 0:
                                currentPlayer.hp -= damage
                            else:
                                currentPlayer.kill()
                                bullet.player.killPlayer(currentPlayer)
                        continue

                    if collide_head_player:
                        # print(collide_player)
                        for currentPlayer in collide_head_player:
                            currentPlayer: Player
                            by = bullet.by
                            head_damage = Players[by].weapon.head_damage

                            if currentPlayer.reborn_defend_tick > 0:
                                head_damage = 0

                            if currentPlayer.team == bullet.player.team:
                                head_damage /= 2

                            if currentPlayer.hp - head_damage > 0:
                                currentPlayer.hp -= head_damage
                            else:
                                currentPlayer.kill()
                                bullet.player.killPlayer(currentPlayer)
                        continue

                    # 子弹对撞
                    left_index = index
                    right_index = index

                    while left_index - 1 >= 0:
                        left_index -= 1
                        # print(left_index)
                        other_bullet = bullets[left_index]
                        if other_bullet.dead:
                            continue
                        if other_bullet.player.team == bullet.player.team:
                            continue

                        my_radius = bullet.bullet_radius_collision
                        my_position = bullet.position()

                        other_body = other_bullet.bullet_body
                        other_radius = other_bullet.bullet_radius_collision
                        other_position = other_body.position

                        if abs(other_position.x - my_position[0]) > other_radius + my_radius:
                            break

                        if collide_circle(my_position, my_radius, other_position,
                                          other_radius):

                            bullet.hp -= other_bullet.damage
                            if bullet.hp <= 0:
                                bullet.dead = True

                            other_bullet.hp -= bullet.damage
                            if other_bullet.hp <= 0:
                                other_bullet.dead = True

                    while right_index + 1 < len(bullets):
                        right_index += 1
                        # print(right_index)
                        other_bullet = bullets[right_index]
                        if other_bullet.dead:
                            continue
                        if other_bullet.player.team == bullet.player.team:
                            continue

                        my_radius = bullet.bullet_radius_collision
                        my_position = bullet.position()

                        other_body = other_bullet.bullet_body
                        other_radius = other_bullet.bullet_radius_collision
                        other_position = other_body.position

                        if abs(other_position.x - my_position[0]) > other_radius + my_radius:
                            break

                        if collide_circle(my_position, my_radius, other_position,
                                          other_radius):
                            bullet.hp -= other_bullet.damage
                            if bullet.hp <= 0:
                                bullet.dead = True

                            other_bullet.hp -= bullet.damage
                            if other_bullet.hp <= 0:
                                other_bullet.dead = True

                    if bullet.dead:
                        continue

                    # 边缘碰撞
                    if not 0 < bullet_body.position.x < width or not 0 < bullet_body.position.y < height:
                        # 子弹到达边缘消失
                        bullet.dead = True
                        continue

                    # 地图碰撞
                    if map_image.get_at((int(bullet_body.position.x), int(bullet_body.position.y))) != (
                            255, 255, 255, 255):
                        # 子弹碰到障碍物时消失
                        bullet.dead = True
                        continue

                    # 不消失，添加回去
                    new_bullets.append(bullet)
                    x, y = bullet_body.position.int_tuple
                    new_bullets_message.append([x, y, bullet.bullet_radius])
                    if current_spacetick == space_tick - 1:
                        new_bullets_sandbox.append(Bullet_Sandbox(bullet))

                bullets = new_bullets
                bullets_message = new_bullets_message
                if current_spacetick == space_tick - 1:
                    bullets_sandbox = new_bullets_sandbox

            new_grenades = []
            new_grenades_message = []
            new_grenades_sandbox = []

            for grenade in grenades:
                grenade: Grenade_grenade
                grenade.update()

                if grenade.dead:
                    continue

                x, y = grenade.position()
                new_grenades.append(grenade)
                new_grenades_message.append([x, y, grenade.gunType, grenade.damage, grenade.damage_radius])
                new_grenades_sandbox.append(Grenade_Sandbox(grenade))

            grenades = new_grenades
            grenades_message = new_grenades_message
            grenades_sandbox = new_grenades_sandbox

            new_kunais = []
            new_kunais_message = []

            for kunai in kunais:
                kunai: Kunai

                if kunai.player.invalid:
                    continue

                if kunai.mode == 1 and not kunai.stop:
                    # 子弹移动
                    kunai.bullet_body.position += kunai.bullet_body.velocity * (1.0 / fps)

                    kunai.update()

                    # 边缘碰撞
                    if not Kunai.barrier_offset < kunai.bullet_body.position.x < width - Kunai.barrier_offset or not Kunai.barrier_offset < kunai.bullet_body.position.y < height - Kunai.barrier_offset:
                        kunai.stopMoving()

                    # 地图碰撞
                    if map_image.get_at((int(kunai.bullet_body.position.x), int(kunai.bullet_body.position.y))) != (
                            255, 255, 255, 255):
                        kunai.stopMoving()
                elif kunai.mode == 2:
                    kunai.bullet_body.position = kunai.player.character.attachment.position()

                new_kunais.append(kunai)
                x, y = kunai.position()
                new_kunais_message.append([x, y, kunai.player.name])

            kunais = new_kunais
            kunais_message = new_kunais_message

            timeLogger.endPoint("timecost_physics")

            timeLogger.addPoint("timecost_broadcast")

            players_message = {}
            for currentPlayer in Players.values():
                players_message[currentPlayer.name] = [currentPlayer.position(), currentPlayer.head_pos,
                                                       currentPlayer.hp,
                                                       currentPlayer.weapon.bulletNow, currentPlayer.weapon.bulletLeft,
                                                       currentPlayer.weapon.gunType,
                                                       max(currentPlayer.weapon.reload_cd, currentPlayer.changeGun_CD),
                                                       currentPlayer.reborn_defend_tick,
                                                       currentPlayer.team, currentPlayer.character.type,
                                                       currentPlayer.state]
                if currentPlayer.character.type == 1:
                    players_message[currentPlayer.name].append(currentPlayer.shift_tick)
                if currentPlayer.character.type == 2:
                    character: Character_YellowFlash = currentPlayer.character
                    players_message[currentPlayer.name] += [character.skill_state]
                    if character.skill_state == 10 or character.skill_state == 20:
                        players_message[currentPlayer.name] += [character.cd]
                    elif character.skill_state == 12:
                        players_message[currentPlayer.name] += [character.Mode1_maintainTime]

                if currentPlayer.character.type == 3:
                    character: Character_RedMoonObito = currentPlayer.character
                    players_message[currentPlayer.name] += [character.fade_time, character.fade_time_constant,
                                                            character.switch_time, character.switch_time_constant,
                                                            character.cd, character.skill_state]

            message = {"type": "info",
                       "players": players_message,
                       "bullets": bullets_message,
                       "grenades": grenades_message,
                       "kunais": kunais_message}
            # print(message)
            await broadcast_message(json.dumps(message))

            for m in awaitingMessage:
                await broadcast_message(m)
            awaitingMessage.clear()

            if tickcount % 8 == 0:
                players_message_weapon = {}
                players_message_money = {}
                players_message_emoji = {}
                for currentPlayer in Players.values():
                    players_message_weapon[currentPlayer.name] = [weapon.gunType if weapon else 0 for weapon in
                                                                  currentPlayer.weaponList]
                    players_message_money[currentPlayer.name] = currentPlayer.money
                    players_message_emoji[currentPlayer.name] = currentPlayer.emoji

                message = {"type": "misc",
                           "weapons": players_message_weapon, "money": players_message_money,
                           "emoji": players_message_emoji}
                await broadcast_message(json.dumps(message))

            timeLogger.endPoint("timecost_broadcast")

            timeLogger.endPoint("timecost_total")

            totalcost = time.time() - timeLogger.get("timecost_total")

            for info, t in timeLogger.show():
                rate = format_nf(t / totalcost * 100, n=1)
                print(f"事件{info}：耗时{format_nf(t)}, 占比{rate}%", end='\n')

            print(f"总耗时:{format_nf(totalcost, n=1)}")
            print(f"总耗时占比:{format_nf(totalcost / (1 / fps) * 100, n=1)}%")

            timesleep = 1 / fps - totalcost
            # timesleep = 1 / fps - totalcost - extra_timesleep

            if timesleep <= 0:
                mainLogger.error(f"ERROR: timesleep = {timesleep}")
                # mainLogger.error(f"ERROR: timesleep = {timesleep}, extra_timesleep = {extra_timesleep}")
                # extra_timesleep = -timesleep

                timesleep_error_info = ""
                for info, t in timeLogger.show():
                    rate = format_nf(t / totalcost * 100, n=1)
                    timesleep_error_info += f"事件{info}：耗时{format_nf(t)}, 占比{rate}%\n"
                mainLogger.error(timesleep_error_info)

            else:
                # print(f"timesleep: {timesleep}")
                await asyncio.sleep(timesleep)
        except Exception as e:
            error_info = traceback.format_exc()
            mainLogger.error(f"Error occurs when Judge: {e}\nDetailed info:\n{error_info}")
            ERRORTIMES_JUDGE += 1
            if ERRORTIMES_JUDGE > 1000:
                mainLogger.exception(f"ERRORTIMES_JUDGE > 1000! Stopping the program!")
                running = False

    mainLogger.critical(f"\n----------\nExiting!\n----------\n")
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    asyncio.run(main(port=11002))
