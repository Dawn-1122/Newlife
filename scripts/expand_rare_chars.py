"""
扩充生僻字（二级字表 + 意象美生僻字）

方案 A（已拍板）：全量引入《通用规范汉字表》二级字表 3000 字 + 从新字源
recommend_chars 收集的「意象美生僻字」（徐长卿/白芷/青黛/半夏/杜若/白薇/黄芪/望舒/扶苏 等）。

关键原则：新字一律默认 luck=吉，仅负面义入黑名单，不因生僻标凶。
生僻度（level）仅数据治理，绝不参与评分。

数据来源：
- 康熙笔画：data/dict/kangxi_strokes.json（权威对照表，如缺失则跳过全量二级字扩充）
- 二级字表：data/dict/level_2_chars.txt（《通用规范汉字表》二级字 3000，如缺失则跳过）
- 拼音：pypinyin
- 部首：data/dict/radical_map.json（字→部首，如缺失则从生僻字表的部首字段取）
- 意象美生僻字：本脚本内置 CURATED_IMAGERY_CHARS（人工精编，含 meaning/detail/imagery）

用法：
    venv/bin/python scripts/expand_rare_chars.py
"""

import json
import re
from pathlib import Path
from pypinyin import pinyin, Style

ROOT = Path(__file__).resolve().parent.parent
CHARS_PATH = ROOT / "data" / "dict" / "chars.json"

# 可选外部数据源（缺失则优雅跳过，只做「意象美生僻字」精编扩充）
KX_STROKES_PATH = ROOT / "data" / "dict" / "kangxi_strokes.json"
LEVEL2_PATH = ROOT / "data" / "dict" / "level_2_chars.txt"
RADICAL_MAP_PATH = ROOT / "data" / "dict" / "radical_map.json"

# ── 部首 → 五行映射（复用 expand_char_db.py 的命名学主流划分） ──
WUXING_RADICAL = {
    "金": "金", "釒": "金", "刀": "金", "刂": "金", "戈": "金", "矛": "金",
    "辛": "金", "言": "金", "車": "金", "酉": "金", "貝": "金", "齒": "金",
    "走": "金", "足": "金", "骨": "金", "白": "金", "革": "金", "艮": "金",
    "口": "金", "寸": "金", "十": "金", "殳": "金", "匕": "金", "音": "金",
    "非": "金", "見": "金", "牙": "金",
    "木": "木", "艸": "木", "艹": "木", "竹": "木", "禾": "木", "米": "木",
    "耒": "木", "瓜": "木", "桑": "木", "黍": "木", "韭": "木", "片": "木",
    "爿": "木", "乙": "木", "力": "木", "手": "木", "扌": "木", "爪": "木",
    "支": "木", "廾": "木", "糸": "木", "虫": "木", "目": "木", "衣": "木",
    "巾": "木", "弓": "木", "网": "木", "干": "木", "毛": "木", "虍": "木",
    "豆": "木", "几": "木", "卜": "木", "青": "木",
    "水": "水", "氵": "水", "雨": "水", "冫": "水", "魚": "水", "風": "水",
    "辵": "水", "彳": "水", "舟": "水", "耳": "水", "子": "水", "文": "水",
    "黑": "水", "豕": "水", "巛": "水", "行": "水",
    "火": "火", "灬": "火", "日": "火", "光": "火", "赤": "火", "心": "火",
    "忄": "火", "示": "火", "礻": "火", "攴": "火", "攵": "火", "馬": "火",
    "鳥": "火", "鸟": "火", "隹": "火", "羽": "火", "靑": "火", "頁": "火",
    "疒": "火", "欠": "火", "立": "火", "矢": "火", "彡": "火", "舌": "火",
    "鬼": "火", "方": "火", "小": "火", "斗": "火", "斤": "火",
    "土": "土", "山": "土", "石": "土", "田": "土", "玉": "土", "王": "土",
    "邑": "土", "阜": "土", "阝": "土", "宀": "土", "冖": "土", "厂": "土",
    "广": "土", "尸": "土", "囗": "土", "凵": "土", "門": "土", "戶": "土",
    "穴": "土", "儿": "土", "人": "土", "亻": "土", "大": "土", "女": "土",
    "肉": "土", "月": "土", "皿": "土", "用": "土", "曰": "土", "犬": "土",
    "食": "土", "牛": "土", "止": "土", "工": "土", "士": "土", "己": "土",
    "匸": "土", "户": "土", "臼": "土", "冂": "土", "匚": "土", "父": "土",
    "里": "土", "身": "土", "辰": "土", "一": "土", "丨": "土",
    "丶": "土", "丿": "土", "乚": "土", "二": "土", "亠": "土", "八": "土",
    "入": "土", "勹": "土", "夕": "土", "又": "土",
}
# 补充传统康熙部首（kx_full.xlsx 部首为繁体，覆盖常见缺项）
WUXING_RADICAL.update({
    "韋": "金", "韦": "金", "革": "金",
    "羊": "土", "角": "木", "谷": "土", "長": "火", "面": "土",
    "香": "水", "甘": "土", "生": "金", "用": "土", "皮": "土",
    "血": "火", "老": "土", "而": "土", "至": "土", "色": "土",
    "缶": "土", "釆": "火", "采": "火", "飛": "水", "首": "土",
    "麥": "木", "麦": "木", "麻": "木", "黃": "土", "黄": "土",
    "鹿": "火", "鼠": "水", "鼻": "土", "龍": "火", "龙": "火",
    "龜": "水", "龟": "水", "龠": "木", "毋": "土", "襾": "土",
    "髟": "木", "高": "木", "鬥": "火", "鬯": "水", "鹵": "土",
})
DEFAULT_WUXING = "土"

# 负面字黑名单（起名避讳，标「凶」）
BAD_CHARS = set(
    "死亡病灾凶杀祸仇怨恨悲惨哀残暴恶劣丑邪奸盗贼毒瘟疫鬼怪妖魔贱奴囚败衰堕"
    "伤损破崩溃裂断灭绝亡丧埋葬殡灰烬寒苦穷贫饥馑灾殃厄祸患难危殆殇殁殂殒"
)

# ── 意象美生僻字（人工精编：来源山海经/本草纲目/楚辞，level=扩展） ──
# 字段：char/radical/kangxi_strokes/wuxing/meaning/shuowen/detail/imagery
CURATED_IMAGERY_CHARS = [
    {
        "char": "黛", "radical": "黑", "kangxi_strokes": 17, "wuxing": "水",
        "meaning": "青黛、眉黛，象征清雅、沉静、温婉",
        "shuowen": "画眉也。从黑，朕声。",
        "detail": "本义为青黑色颜料，古代女子以黛画眉，故「黛」常喻女子眉目之美与温婉沉静。青黛亦入药。起名取眉黛青颦、清雅沉静之意。",
        "imagery": ["青黛", "清雅", "沉静"],
    },
    {
        "char": "芪", "radical": "艹", "kangxi_strokes": 9, "wuxing": "木",
        "meaning": "黄芪，补气固表，象征温厚、补益",
        "shuowen": "芪母也。从艸，氏声。",
        "detail": "本义为黄芪，一味补气名药。《本草纲目》载其「补气固表」。起名取温厚补益、生机内蕴之意。",
        "imagery": ["草药", "补益", "温厚"],
    },
    {
        "char": "芍", "radical": "艹", "kangxi_strokes": 9, "wuxing": "木",
        "meaning": "芍药，象征柔美、温婉、美好",
        "shuowen": "芍药也。从艸，勺声。",
        "detail": "本义为芍药，花大而美，古称「花相」。白芍入药养血柔肝。起名取芍药之柔美温婉、绰约多姿之意。",
        "imagery": ["草药", "柔美", "温婉"],
    },
    {
        "char": "茯", "radical": "艹", "kangxi_strokes": 12, "wuxing": "木",
        "meaning": "茯苓，健脾宁心，象征清雅、宁和",
        "shuowen": "茯苓也。从艸，伏声。",
        "detail": "本义为茯苓，菌类药材，寄生于松根。《本草纲目》载其「健脾宁心」。起名取清雅宁和、含蓄内敛之意。",
        "imagery": ["草药", "清雅", "宁和"],
    },
    {
        "char": "苓", "radical": "艹", "kangxi_strokes": 11, "wuxing": "木",
        "meaning": "茯苓之苓，象征清雅、灵秀、宁和",
        "shuowen": "卷耳也。从艸，令声。",
        "detail": "本义为卷耳草，亦为茯苓之「苓」。与「茯」连用为茯苓，喻清雅灵秀、淡泊宁和。起名取灵秀清雅之意。",
        "imagery": ["草药", "清雅", "灵秀"],
    },
    {
        "char": "蘅", "radical": "艹", "kangxi_strokes": 20, "wuxing": "木",
        "meaning": "杜蘅，香草，象征高洁、清雅、幽芳",
        "shuowen": "杜蘅，香草也。从艸，衡声。",
        "detail": "本义为杜蘅，一种香草，即杜若。《楚辞》多以蘅兰喻君子高洁。起名取香草之幽芳、品行高洁之意。",
        "imagery": ["香草", "清雅", "高洁"],
    },
    {
        "char": "蘩", "radical": "艹", "kangxi_strokes": 22, "wuxing": "木",
        "meaning": "白蒿，象征质朴、清雅、生机",
        "shuowen": "白蒿也。从艸，繁声。",
        "detail": "本义为白蒿，古可入食入药。《诗经》「于以采蘩」写采蘩之景。起名取质朴清雅、生生不息之意。",
        "imagery": ["香草", "质朴", "清雅"],
    },
    {
        "char": "荇", "radical": "艹", "kangxi_strokes": 12, "wuxing": "木",
        "meaning": "荇菜，浮水而生，象征清雅、灵动",
        "shuowen": "荇菜也。从艸，行声。",
        "detail": "本义为荇菜，一种浮水植物。《诗经》「参差荇菜，左右流之」写其灵动之姿。起名取清雅灵动、随水自适之意。",
        "imagery": ["水草", "清雅", "灵动"],
    },
    {
        "char": "枸", "radical": "木", "kangxi_strokes": 9, "wuxing": "木",
        "meaning": "枸杞之枸，象征滋补、坚韧、祥瑞",
        "shuowen": "木也。可为酱。从木，句声。",
        "detail": "本义为枸杞，果实滋补，《神农本草经》载其「久服坚筋骨」。与「杞」连用为枸杞。起名取滋补祥瑞、坚韧长青之意。",
        "imagery": ["草木", "滋补", "祥瑞"],
    },
    {
        "char": "杞", "radical": "木", "kangxi_strokes": 7, "wuxing": "木",
        "meaning": "枸杞之杞，象征祥瑞、坚贞、安康",
        "shuowen": "枸杞也。从木，己声。",
        "detail": "本义为枸杞，与「枸」连用。古人以杞为祥瑞长寿之木。起名取坚贞安康、祥瑞长青之意。",
        "imagery": ["草木", "祥瑞", "安康"],
    },
    {
        "char": "孚", "radical": "子", "kangxi_strokes": 7, "wuxing": "水",
        "meaning": "诚信、信服，象征忠信、通达",
        "shuowen": "卵孚也。从爪，从子。",
        "detail": "本义为孵卵、诚信。《周易》「中孚」卦取诚信之义，「信及豚鱼」。起名取诚信忠信、通达人心之意。",
        "imagery": ["诚信", "忠信", "通达"],
    },
    {
        "char": "鸾", "radical": "鸟", "kangxi_strokes": 30, "wuxing": "火",
        "meaning": "鸾鸟，神鸟，象征祥瑞、安宁、美好",
        "shuowen": "赤神灵之精也。从鸟，䜌声。",
        "detail": "本义为鸾鸟，凤凰之属，古人以为祥瑞。《山海经》「鸾鸟见则天下安宁」。起名取祥瑞安宁、美好高洁之意。",
        "imagery": ["神鸟", "祥瑞", "安宁"],
    },
    {
        "char": "榖", "radical": "木", "kangxi_strokes": 16, "wuxing": "木",
        "meaning": "构树，古之祥木，象征明慧、清雅",
        "shuowen": "楮也。从木，殻声。",
        "detail": "本义为构树（榖树）。《山海经》载「迷榖」之木，「佩之不迷」。起名取明慧清雅、不迷于途之意。",
        "imagery": ["草木", "明慧", "清雅"],
    },
    {
        "char": "蘼", "radical": "艹", "kangxi_strokes": 25, "wuxing": "木",
        "meaning": "蘼芜，香草，象征幽芳、清雅",
        "shuowen": "蘼芜也。从艸，靡声。",
        "detail": "本义为蘼芜，香草名。《楚辞》「秋兰兮蘼芜」写香草之美。起名取幽芳清雅、兰心蕙质之意。",
        "imagery": ["香草", "幽芳", "清雅"],
    },
    {
        "char": "薜", "radical": "艹", "kangxi_strokes": 20, "wuxing": "木",
        "meaning": "薜荔，香草，象征坚韧、清雅",
        "shuowen": "牡赞也。从艸，辟声。",
        "detail": "本义为薜荔，蔓生香草，攀援而生。《楚辞》多咏之。起名取坚韧清雅、攀援向上之意。",
        "imagery": ["香草", "坚韧", "清雅"],
    },
    {
        "char": "蘧", "radical": "艹", "kangxi_strokes": 22, "wuxing": "木",
        "meaning": "蘧麦、蘧然，象征清雅、超然",
        "shuowen": "蘧麦也。从艸，遽声。",
        "detail": "本义为蘧麦，草名；「蘧然」又喻超然自适之态。起名取清雅超然、淡泊从容之意。",
        "imagery": ["草木", "清雅", "超然"],
    },
    {
        "char": "茝", "radical": "艹", "kangxi_strokes": 10, "wuxing": "木",
        "meaning": "白芷，香草，象征高洁、芬芳",
        "shuowen": "虈也。从艸，臣声。",
        "detail": "本义为白芷，香草名。《楚辞》「既替余以蕙纕兮，又申之以揽茝」以茝喻高洁。起名取芬芳高洁之意。",
        "imagery": ["香草", "高洁", "芬芳"],
    },
    {
        "char": "蓠", "radical": "艹", "kangxi_strokes": 19, "wuxing": "木",
        "meaning": "江蓠，香草，象征清雅、高洁",
        "shuowen": "江蓠，蘼芜也。从艸，离声。",
        "detail": "本义为江蓠，香草名，即蘼芜。《离骚》「扈江蓠与辟芷兮」写佩戴香草喻修洁。起名取清雅高洁之意。",
        "imagery": ["香草", "清雅", "高洁"],
    },
    {
        "char": "荪", "radical": "艹", "kangxi_strokes": 15, "wuxing": "木",
        "meaning": "香草，象征高洁、芬芳、美好",
        "shuowen": "香艸也。从艸，孙声。",
        "detail": "本义为香草名，古以荪喻君子高洁之德。《楚辞》多以荪兰并称。起名取芬芳高洁、美好德馨之意。",
        "imagery": ["香草", "高洁", "芬芳"],
    },
]


def gen_pinyin(char: str) -> tuple[str, int]:
    """用 pypinyin 生成拼音（无声调）和声调数字。"""
    try:
        normal = pinyin(char, style=Style.NORMAL)
        tone3 = pinyin(char, style=Style.TONE3)
        py = normal[0][0] if normal else ""
        t = 0
        if tone3 and tone3[0]:
            m = re.search(r"(\d)$", tone3[0][0])
            if m:
                t = int(m.group(1))
        return py, t
    except Exception:
        return "", 0


def get_wuxing(char: str, radical: str) -> str:
    if radical and radical in WUXING_RADICAL:
        return WUXING_RADICAL[radical]
    return DEFAULT_WUXING


def load_json_optional(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def expand_level2(kx_strokes: dict, radical_map: dict, level2: list[str], existing: set) -> list[dict]:
    """从二级字表 + 康熙笔画表构造 level=二 的字条目（纯数据获取，无需 LLM）。"""
    added: list[dict] = []
    for char in level2:
        if char in existing or char not in kx_strokes:
            continue
        py, tone = gen_pinyin(char)
        radical = radical_map.get(char, "")
        entry = {
            "char": char,
            "pinyin": py,
            "tone": tone,
            "radical": radical,
            "kangxi_strokes": kx_strokes[char],
            "simplified_strokes": kx_strokes[char],
            "wuxing": get_wuxing(char, radical),
            "luck": "凶" if char in BAD_CHARS else "吉",
            "gender": "中",
            "meaning": "",
            "shuowen": "",
            "detail": "",
            "imagery": [],
            "level": "二",
        }
        added.append(entry)
        existing.add(char)
    return added


def build_curated(existing: set) -> list[dict]:
    """把人工精编的意象美生僻字构造成 level=扩展 条目。"""
    added: list[dict] = []
    for item in CURATED_IMAGERY_CHARS:
        char = item["char"]
        if char in existing:
            continue
        py, tone = gen_pinyin(char)
        entry = {
            "char": char,
            "pinyin": py,
            "tone": tone,
            "radical": item["radical"],
            "kangxi_strokes": item["kangxi_strokes"],
            "simplified_strokes": item["kangxi_strokes"],
            "wuxing": item["wuxing"],
            "luck": "吉",
            "gender": "中",
            "meaning": item["meaning"],
            "shuowen": item["shuowen"],
            "detail": item["detail"],
            "imagery": item["imagery"],
            "level": "扩展",
        }
        added.append(entry)
        existing.add(char)
    return added


def main() -> None:
    with open(CHARS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 现有字补 level 字段（一级字库）
    for c in data["chars"]:
        c.setdefault("level", "一")
        c.setdefault("imagery", [])
    existing = {c["char"] for c in data["chars"]}

    # 1) 意象美生僻字（精编，level=扩展）
    curated = build_curated(existing)
    data["chars"].extend(curated)

    # 2) 二级字表全量（如外部数据就绪）
    kx_strokes = load_json_optional(KX_STROKES_PATH)
    radical_map = load_json_optional(RADICAL_MAP_PATH)
    level2_path = LEVEL2_PATH
    level2_chars: list[str] = []
    if level2_path.exists():
        with open(level2_path, "r", encoding="utf-8") as f:
            level2_chars = [line.strip() for line in f if line.strip()]
    level2_added: list[dict] = []
    if kx_strokes and level2_chars:
        level2_added = expand_level2(kx_strokes, radical_map, level2_chars, existing)
        data["chars"].extend(level2_added)
    else:
        print("[expand-rare] 未找到二级字表/康熙笔画数据，跳过全量二级字扩充（仅精编意象生僻字）")

    data["total"] = len(data["chars"])
    data["version"] = "4.0"

    # 统计五行分布
    wx_count = {}
    for c in data["chars"]:
        wx = c.get("wuxing", "")
        wx_count[wx] = wx_count.get(wx, 0) + 1
    data["wuxing_distribution"] = wx_count

    # 统计等级分布
    level_count = {}
    for c in data["chars"]:
        lv = c.get("level", "一")
        level_count[lv] = level_count.get(lv, 0) + 1
    data["level_distribution"] = level_count

    with open(CHARS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[expand-rare] 精编意象生僻字 +{len(curated)}，二级字 +{len(level2_added)}")
    print(f"[expand-rare] 字库总数 {data['total']}，版本 {data['version']}")
    print(f"[expand-rare] 五行分布: {wx_count}")
    print(f"[expand-rare] 等级分布: {level_count}")


if __name__ == "__main__":
    main()
