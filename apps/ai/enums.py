"""Quick Entry 枚举与派生规则的唯一实现。

三处共用：生成提示词、/validate 确定性校验、前端下拉。
改这里就是改口径，不要在别处另写一份。
"""

STAGES = ('primary', 'junior', 'senior')

STAGE_NAMES = {'primary': '小学', 'junior': '初中', 'senior': '高中'}

SUBJECTS = ('语文', '数学', '英语', '物理', '化学', '生物', '政治', '历史', '地理')

# 学科必须收敛成上面九个值。AI 会自行产出“生物学”“道法”这类变体，
# 变体不归位就会导致知识点目录、题型字典、指纹全部对不上。
SUBJECT_ALIASES = {
    '生物学': '生物', '生物': '生物',
    '道法': '政治', '道德与法治': '政治', '思想政治': '政治', '政治与法治': '政治',
    '思想品德': '政治', '品德与社会': '政治',
    '历史与社会': '历史',
    'chinese': '语文', 'math': '数学', 'english': '英语', 'physics': '物理',
    'chemistry': '化学', 'biology': '生物', 'politics': '政治', 'history': '历史',
    'geography': '地理',
}

STAGE_ALIASES = {
    '小学': 'primary', '初中': 'junior', '高中': 'senior',
    'primary': 'primary', 'junior': 'junior', 'senior': 'senior',
}

# 来源字典的性质：题库按它区分教辅与公开卷
SOURCE_NATURES = ('教辅', '校本', '公开', '其他')

GRADES = (('g1', '一年级'), ('g2', '二年级'), ('g3', '三年级'), ('g4', '四年级'), ('g5', '五年级'),
          ('g6', '六年级'), ('g7', '初一'), ('g8', '初二'), ('g9', '初三'),
          ('g10', '高一'), ('g11', '高二'), ('g12', '高三'))

GRADE_ALIASES = {
    '小一': 'g1', '小二': 'g2', '小三': 'g3', '小四': 'g4', '小五': 'g5', '小六': 'g6',
    '一年级': 'g1', '二年级': 'g2', '三年级': 'g3', '四年级': 'g4', '五年级': 'g5', '六年级': 'g6',
    '初一': 'g7', '初二': 'g8', '初三': 'g9',
    '七年级': 'g7', '八年级': 'g8', '九年级': 'g9',
    '高一': 'g10', '高二': 'g11', '高三': 'g12',
    '高1': 'g10', '高2': 'g11', '高3': 'g12',
}

SEMESTERS = (('1', '秋季'), ('2', '春季'))

# 试卷质量等级：AI 综合评估后给出，人工可改
QUALITY_LEVELS = ('精品', '普通', '待修')

QUALITY_ALIASES = {'high': '精品', 'normal': '普通', 'low': '待修', 'good': '精品', 'bad': '待修'}

SEMESTER_ALIASES = {'1': '1', '上': '1', '上学期': '1', '第一学期': '1', '秋': '1', '秋季': '1',
                    '2': '2', '下': '2', '下学期': '2', '第二学期': '2', '春': '2', '春季': '2'}

_GRADE_CODES = {code for code, _ in GRADES}

# 26 个卷型：25 个组卷网原值 + 其他（AI 无法归类时的兜底，占比用于发现枚举缺口）
PAPER_TYPES = (
    '课前预习', '课堂例题', '随堂练习', '课后作业', '单元复习',
    '单元测试', '阶段检测', '期中', '期末', '开学考试',
    '专题练习', '竞赛',
    '学业考试', '中考真题', '高考真题', '小升初真题', '强基计划',
    '中考模拟', '高考模拟', '小升初模拟',
    '中考复习', '高考复习', '小升初复习', '小升初衔接', '初升高衔接',
    '其他',
)

PAPER_TYPE_NATURE = {
    '课前预习': '同步', '课堂例题': '同步', '随堂练习': '同步', '课后作业': '同步',
    '单元复习': '同步', '单元测试': '同步', '阶段检测': '同步', '期中': '同步',
    '期末': '同步', '开学考试': '同步',
    '专题练习': '专题', '中考复习': '专题', '高考复习': '专题', '小升初复习': '专题',
    '小升初衔接': '专题', '初升高衔接': '专题',
    '竞赛': '竞赛',
    '学业考试': '真题', '中考真题': '真题', '高考真题': '真题',
    '小升初真题': '真题', '强基计划': '真题',
    '中考模拟': '模拟', '高考模拟': '模拟', '小升初模拟': '模拟',
}

NATURES = ('真题', '模拟', '同步', '专题', '竞赛')

# 考试阶段按性质分组：跨组的值属于脏数据
NATURE_STAGES = {
    '真题': ('高考', '中考', '学业水平', '小升初', '强基计划'),
    '模拟': ('一模', '二模', '三模', '联考', '摸底'),
    '同步': ('单元测试', '阶段检测', '期中', '期末', '开学考'),
    '专题': (),
    '竞赛': (),
}

# 卷名解析用的阶段词表（仅用于给 AI 与人工提供候选，解析仍由模型判断）
STAGE_KEYWORDS = {
    '一模': ('一模', '第一次模拟', '一诊', '一模考'),
    '二模': ('二模', '第二次模拟', '二诊'),
    '三模': ('三模', '第三次模拟', '三诊'),
    '联考': ('联考', '多校联考', '八省联考'),
    '摸底': ('摸底', '零模', '学情调研', '起点考'),
    '单元测试': ('单元测试', '单元测'),
    '阶段检测': ('阶段检测', '月考', '阶段测'),
    '期中': ('期中',),
    '期末': ('期末',),
    '开学考': ('开学考', '开学考试', '入学考'),
    '高考': ('高考', '高考试题'),
    '中考': ('中考', '中考试题'),
    '学业水平': ('学业水平', '学考', '会考', '合格考'),
    '小升初': ('小升初',),
    '强基计划': ('强基',),
}

# 各学段可选的卷型：把跨学段的矛盾值挡在界面上
_PAPER_TYPES_COMMON = (
    '课前预习', '课堂例题', '随堂练习', '课后作业', '单元复习',
    '单元测试', '阶段检测', '期中', '期末', '开学考试',
    '专题练习', '竞赛',
)

PAPER_TYPES_BY_STAGE = {
    'primary': _PAPER_TYPES_COMMON + ('小升初真题', '小升初模拟', '小升初复习', '其他'),
    'junior': _PAPER_TYPES_COMMON + ('中考真题', '中考模拟', '中考复习', '初升高衔接',
                                     '学业考试', '其他'),
    'senior': _PAPER_TYPES_COMMON + ('高考真题', '高考模拟', '高考复习', '强基计划',
                                     '学业考试', '其他'),
}

# 旧口径（同步练/单元测/月考/真题/模拟…）→ 新口径。存量数据靠它一次性归位。
LEGACY_PAPER_TYPE_ALIASES = {
    '同步练': '课后作业',
    '单元测': '单元测试',
    '月考': '阶段检测',
    '一模二模': '其他',
    '真题': '其他',
    '模拟': '其他',
    '课时作业': '课后作业',
}

SUB_TYPES = ('single', 'group')
# single=单题（材料并入题干）；group=题组（材料被两道及以上小题共用）
GRADING_METHODS = ('program', 'ai')
# program=程序批阅（只需比对字母或判断勾叉）；ai=需模型批阅
DIFFICULTY_BANDS = ('容易', '适中', '困难')

# 模型常按 5 档说难度，统一折成 3 档；档位最终由数值派生，这里只做兜底归一。
BAND_ALIASES = {'简单': '容易', '较易': '容易', '容易': '容易',
                '中等': '适中', '适中': '适中',
                '较难': '困难', '困难': '困难'}


def derive_band(value) -> str:
    """得分率 → 三档：≥0.80 容易，0.50~0.80 适中，<0.50 困难。"""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return ''
    if score >= 0.8:
        return '容易'
    if score >= 0.5:
        return '适中'
    return '困难'


def normalize_band(value: str) -> str:
    return BAND_ALIASES.get(str(value or '').strip(), '')


def normalize_paper_type(value: str):
    """返回 (规范化卷型, 是否被改动)。认不出的值归入「其他」。"""
    text = (value or '').strip()
    if not text:
        return '', False
    if text in PAPER_TYPES:
        return text, False
    alias = LEGACY_PAPER_TYPE_ALIASES.get(text)
    if alias:
        return alias, True
    return '其他', True


def normalize_grade(value: str):
    text = (value or '').strip()
    if not text:
        return '', False
    if text in _GRADE_CODES:
        return text, False
    alias = GRADE_ALIASES.get(text)
    if alias:
        return alias, True
    return text, False


def normalize_semester(value):
    text = str(value or '').strip()
    if not text:
        return '', False
    if text in ('1', '2'):
        return text, False
    alias = SEMESTER_ALIASES.get(text)
    if alias:
        return alias, True
    return text, False


def normalize_quality(value: str):
    text = str(value or '').strip()
    if not text:
        return '', False
    if text in QUALITY_LEVELS:
        return text, False
    alias = QUALITY_ALIASES.get(text.lower())
    if alias:
        return alias, True
    return '', True


def normalize_year(value):
    text = str(value or '').strip()
    if not text:
        return '', False
    digits = ''.join(ch for ch in text if ch.isdigit())
    if len(digits) >= 4:
        year = digits[:4]
        return year, year != text
    return text, False


def normalize_subject(value: str):
    """返回 (规范化学科, 是否被改动)。认不出的保留原值，不硬塞。"""
    text = (value or '').strip()
    if not text:
        return '', False
    if text in SUBJECTS:
        return text, False
    alias = SUBJECT_ALIASES.get(text) or SUBJECT_ALIASES.get(text.lower())
    if alias:
        return alias, True
    return text, False


def stage_code(value: str) -> str:
    """中文或代码的学段统一成 primary/junior/senior。"""
    text = (value or '').strip()
    return STAGE_ALIASES.get(text) or STAGE_ALIASES.get(text.lower()) or ''


def normalize_source(item: dict) -> dict:
    """来源条目规范化：名称去空白、性质必须落枚举、id 缺失时按名称生成。"""
    name = str((item or {}).get('name') or '').strip()
    nature = str((item or {}).get('nature') or '').strip()
    source_id = str((item or {}).get('id') or '').strip()
    if not source_id and name:
        source_id = 'src-' + str(abs(hash(name)) % 10 ** 8)
    return {'id': source_id, 'name': name,
            'nature': nature if nature in SOURCE_NATURES else '其他',
            'default': bool((item or {}).get('default'))}


def exam_nature_of(paper_type: str) -> str:
    return PAPER_TYPE_NATURE.get((paper_type or '').strip(), '')


def allowed_exam_stages(nature: str) -> tuple:
    return NATURE_STAGES.get((nature or '').strip(), ())


def allowed_paper_types(stage: str) -> tuple:
    return PAPER_TYPES_BY_STAGE.get((stage or '').strip(), PAPER_TYPES)


def derive_sub_type(subquestions) -> str:
    """题组=材料被两道及以上小题共用；否则单题。纯结构派生，不交语义判断。"""
    return 'group' if len(subquestions or []) >= 2 else 'single'


def normalize_grading_method(value: str) -> str:
    method = (value or '').strip().lower()
    if method in GRADING_METHODS:
        return method
    # 旧口径：auto 是“自动批 = 程序批”，manual 是“人工/模型批”
    if method == 'auto':
        return 'program'
    return 'ai'


def paper_issues(paper: dict) -> list[str]:
    """试卷层确定性校验，返回人可读的问题列表。"""
    issues = []
    attrs = paper.get('attributes') or {}
    value = (paper.get('paper_type') or '').strip()
    if value and value not in PAPER_TYPES:
        issues.append(f'卷型「{value}」不在 26 个取值内')
    nature = exam_nature_of(value)
    stage_value = (attrs.get('exam_stage') or '').strip()
    if stage_value and stage_value not in allowed_exam_stages(nature):
        issues.append(f'考试阶段「{stage_value}」不属于「{nature or "未定性质"}」')
    declared = (paper.get('exam') or {}).get('declared_question_count')
    if isinstance(declared, (int, float)) and declared < 0:
        issues.append('卷面题量不能为负数')
    total = (paper.get('exam') or {}).get('declared_total_score')
    if isinstance(total, (int, float)) and total == 0:
        issues.append('满分录成了 0，未知应为空')
    return issues


def enums_payload() -> dict:
    """给前端下拉用的一份快照。"""
    return {
        'stages': [{'code': code, 'name': STAGE_NAMES[code]} for code in STAGES],
        'subjects': list(SUBJECTS),
        'paper_types': list(PAPER_TYPES),
        'paper_types_by_stage': {key: list(value) for key, value in PAPER_TYPES_BY_STAGE.items()},
        'paper_type_nature': dict(PAPER_TYPE_NATURE),
        'natures': list(NATURES),
        'nature_stages': {key: list(value) for key, value in NATURE_STAGES.items()},
        'sub_types': list(SUB_TYPES),
        'grading_methods': list(GRADING_METHODS),
        'difficulty_bands': list(DIFFICULTY_BANDS),
        'source_natures': list(SOURCE_NATURES),
        'subjects_aliases': dict(SUBJECT_ALIASES),
        'grades': [{'code': code, 'name': name} for code, name in GRADES],
        'semesters': [{'code': code, 'name': name} for code, name in SEMESTERS],
    }
