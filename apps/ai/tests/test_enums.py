"""枚举与派生规则的回归测试：改口径必须先过这里。"""
import pytest

import core
import enums


def test_paper_types_are_26_and_unique():
    assert len(enums.PAPER_TYPES) == 26
    assert '其他' in enums.PAPER_TYPES
    assert len(set(enums.PAPER_TYPES)) == 26


def test_every_paper_type_maps_to_known_nature_except_other():
    for value in enums.PAPER_TYPES:
        nature = enums.exam_nature_of(value)
        if value == '其他':
            assert nature == ''
        else:
            assert nature in enums.NATURES, value


def test_every_nature_has_stage_group():
    for nature in enums.NATURES:
        assert nature in enums.NATURE_STAGES


def test_legacy_paper_type_is_normalized():
    assert enums.normalize_paper_type('单元测') == ('单元测试', True)
    assert enums.normalize_paper_type('月考') == ('阶段检测', True)
    assert enums.normalize_paper_type('课时作业') == ('课后作业', True)
    assert enums.normalize_paper_type('高考模拟') == ('高考模拟', False)
    assert enums.normalize_paper_type('周测') == ('其他', True)
    assert enums.normalize_paper_type('') == ('', False)


def test_exam_stage_must_belong_to_nature():
    assert enums.exam_nature_of('高考模拟') == '模拟'
    assert '一模' in enums.allowed_exam_stages('模拟')
    assert '高考' not in enums.allowed_exam_stages('模拟')
    assert '高考' in enums.allowed_exam_stages('真题')
    assert enums.allowed_exam_stages('专题') == ()


def test_paper_types_are_filtered_by_stage():
    primary = enums.allowed_paper_types('primary')
    senior = enums.allowed_paper_types('senior')
    assert '小升初真题' in primary and '小升初真题' not in senior
    assert '高考真题' in senior and '高考真题' not in primary


def test_sub_type_is_structural():
    assert enums.derive_sub_type([]) == 'single'
    assert enums.derive_sub_type([{'number': '(1)'}]) == 'single'
    assert enums.derive_sub_type([{'number': '3'}, {'number': '4'}]) == 'group'


def test_grading_method_falls_back_to_ai():
    assert enums.normalize_grading_method('program') == 'program'
    assert enums.normalize_grading_method('PROGRAM') == 'program'
    assert enums.normalize_grading_method('manual') == 'ai'
    assert enums.normalize_grading_method('') == 'ai'
    assert enums.normalize_grading_method('机器') == 'ai'


def test_paper_issues_reports_dirty_values():
    paper = {'paper_type': '不存在', 'attributes': {'exam_stage': '一模'},
             'exam': {'declared_total_score': 0, 'declared_question_count': -1}}
    messages = '\n'.join(enums.paper_issues(paper))
    assert '不在 26 个取值内' in messages
    assert '不属于' in messages
    assert '满分录成了 0' in messages
    assert '不能为负数' in messages


def test_clean_paper_has_no_issues():
    paper = {'paper_type': '高考模拟', 'attributes': {'exam_stage': '一模'},
             'exam': {'declared_total_score': 150, 'declared_question_count': 22}}
    assert enums.paper_issues(paper) == []


def test_enums_payload_shape():
    payload = enums.enums_payload()
    for key in ('stages', 'subjects', 'paper_types', 'paper_types_by_stage',
                'paper_type_nature', 'natures', 'nature_stages',
                'sub_types', 'grading_methods', 'difficulty_bands'):
        assert key in payload
    assert len(payload['paper_types']) == 26


def test_paper_inheritance_carries_exam_nature_to_questions():
    paper = {'id': 'p1', 'paper_type': '高考模拟',
             'attributes': {'stage': '高中', 'subject': '数学', 'exam_stage': '一模'}}
    core.normalize_paper(paper)
    assert paper['attributes']['exam_nature'] == '模拟'
    questions = [{'id': 'q1', 'paper_id': 'p1', 'attributes': {}, 'attribute_sources': {}}]
    core.apply_paper_inheritance(paper, questions)
    attributes = questions[0]['attributes']
    assert attributes['exam_nature'] == '模拟'
    assert attributes['exam_stage'] == '一模'
    assert questions[0]['attribute_sources']['exam_nature'] == 'paper'


def test_normalize_paper_clears_mismatched_stage():
    paper = {'id': 'p1', 'paper_type': '课后作业',
             'attributes': {'exam_stage': '高考'}}
    core.normalize_paper(paper)
    assert paper['attributes']['exam_stage'] == ''
    assert paper['attributes']['exam_nature'] == '同步'
    assert any('不匹配' in message for message in paper['issues'])


def test_structure_tags_are_derived_from_shape():
    single = {'stem': '材料与问题在一起', 'subquestions': [], 'attributes': {}}
    core.apply_question_structure_tags(single)
    assert single['attributes']['sub_type'] == 'single'
    assert single['attributes']['question_type_sub'] == 'single'
    assert single['attributes']['grading_method'] == 'ai'

    group = {'stem': '共用材料', 'subquestions': [{'number': '3'}, {'number': '4'}],
             'attributes': {}}
    core.apply_question_structure_tags(group)
    assert group['attributes']['sub_type'] == 'group'

    program = {'stem': '...', 'subquestions': [{'number': '1'}, {'number': '2'}],
               'attributes': {'grading_method': 'program'}}
    core.apply_question_structure_tags(program)
    assert program['attributes']['grading_method'] == 'program'


def test_paper_attributes_include_inherited_snapshot_keys():
    for key in ('exam_stage', 'publisher_name', 'publisher_series'):
        assert key in core.PAPER_ATTRIBUTES


def test_paper_attribute_result_only_fills_blanks():
    paper = {'id': 'p1', 'attributes': {'subject': '数学'}, 'exam': {}, 'paper_type': ''}
    result = {'subject': '英语', 'stage': 'senior', 'paper_type': '高考模拟',
              'exam_stage': '一模', 'declared_total_score': 150,
              'declared_question_count': 22, 'confidence': {'paper_type': 0.9}}
    filled = core.apply_paper_attribute_result(paper, result)
    assert paper['attributes']['subject'] == '数学'      # 已识别的值不被覆盖
    assert paper['attributes']['stage'] == 'senior'
    assert paper['paper_type'] == '高考模拟'
    assert paper['exam']['declared_total_score'] == 150
    assert paper['exam']['declared_question_count'] == 22
    assert paper['attribute_confidence'] == {'paper_type': 0.9}
    assert filled >= 5


def test_paper_attribute_result_ignores_zero_and_unknown_type():
    paper = {'id': 'p1', 'attributes': {}, 'exam': {}, 'paper_type': ''}
    core.apply_paper_attribute_result(
        paper, {'declared_total_score': 0, 'paper_type': '周测'})
    assert paper['exam'].get('declared_total_score') in (None, '')
    assert paper['paper_type'] == '其他'


def test_paper_attribute_failure_does_not_break_pipeline():
    class Broken:
        def json(self, *args, **kwargs):
            raise RuntimeError('模型超时')

    paper = {'id': 'p1', 'title': '某卷', 'attributes': {}, 'exam': {}, 'paper_type': ''}
    doc = {'id': 'd1', 'name': '某卷.pdf', 'role': 'question', 'pages': []}
    try:
        core.apply_paper_attribute_result(
            paper, core.recognize_paper_attributes(Broken(), paper, doc, core.DATA))
    except RuntimeError:
        pass  # 由 compile_result 的 try/except 兜住
    assert paper['attributes'] == {}


def test_local_mineru_bypasses_system_proxy(monkeypatch):
    """本机回环请求必须 trust_env=False，否则系统代理会把它转成 502。"""
    import httpx
    import mineru_local

    seen = {}

    class Response:
        status_code = 200

        def json(self):
            return {'status': 'ok'}

    def fake_get(url, **kwargs):
        seen.update(kwargs, url=url)
        return Response()

    monkeypatch.setenv('MINERU_PROVIDER', 'auto')
    monkeypatch.setattr(httpx, 'get', fake_get)
    assert mineru_local.available(3.0) is True
    assert seen.get('trust_env') is False
    assert seen['url'].endswith('/v1/health')


def test_subject_aliases_collapse_to_nine_values():
    assert enums.normalize_subject('生物学') == ('生物', True)
    assert enums.normalize_subject('道法') == ('政治', True)
    assert enums.normalize_subject('思想政治') == ('政治', True)
    assert enums.normalize_subject('数学') == ('数学', False)
    assert enums.normalize_subject('') == ('', False)
    for value in enums.SUBJECT_ALIASES.values():
        assert value in enums.SUBJECTS


def test_stage_code_accepts_chinese_and_codes():
    assert enums.stage_code('高中') == 'senior'
    assert enums.stage_code('初中') == 'junior'
    assert enums.stage_code('primary') == 'primary'
    assert enums.stage_code('大学') == ''


def test_paper_subject_is_normalized_with_issue():
    paper = {'id': 'p1', 'paper_type': '课后作业', 'attributes': {'subject': '生物学'}}
    core.normalize_paper(paper)
    assert paper['attributes']['subject'] == '生物'
    assert any('九个学科' in message for message in paper['issues'])


def test_source_items_are_normalized():
    item = enums.normalize_source({'name': ' 金榜学案 ', 'nature': '教辅'})
    assert item['name'] == '金榜学案'
    assert item['nature'] == '教辅'
    assert item['id'].startswith('src-')
    assert enums.normalize_source({'name': 'x', 'nature': '乱写'})['nature'] == '其他'
    assert 'source_natures' in enums.enums_payload()


def test_paper_accepts_source_snapshot_keys():
    assert 'source_name' in core.PAPER_ATTRIBUTES
    assert 'source_nature' in core.PAPER_ATTRIBUTES
    # 教材版本/册次归下游，快速录入不再产出
    assert 'textbook_volume' not in core.PAPER_ATTRIBUTES
    assert 'textbook_version' not in core.PAPER_ATTRIBUTES


def test_default_source_fills_empty_paper(monkeypatch):
    monkeypatch.setattr(core, 'default_source',
                        lambda: {'name': '金榜学案', 'nature': '教辅'})
    paper = {'id': 'p1', 'paper_type': '课后作业', 'attributes': {}}
    core.normalize_paper(paper)
    assert paper['attributes']['source_name'] == '金榜学案'
    assert paper['attributes']['source_nature'] == '教辅'
    assert any('默认来源' in message for message in paper['issues'])


def test_default_source_does_not_override_existing(monkeypatch):
    monkeypatch.setattr(core, 'default_source',
                        lambda: {'name': '金榜学案', 'nature': '教辅'})
    paper = {'id': 'p1', 'paper_type': '课后作业',
             'attributes': {'source_name': '金学典', 'source_nature': '教辅'}}
    core.normalize_paper(paper)
    assert paper['attributes']['source_name'] == '金学典'


def test_source_nature_is_inherited_to_questions():
    paper = {'id': 'p1', 'paper_type': '课后作业',
             'attributes': {'source_name': '金榜学案', 'source_nature': '教辅'}}
    core.normalize_paper(paper)
    questions = [{'id': 'q1', 'paper_id': 'p1', 'attributes': {}, 'attribute_sources': {}}]
    core.apply_paper_inheritance(paper, questions)
    assert questions[0]['attributes']['source_name'] == '金榜学案'
    assert questions[0]['attributes']['source_nature'] == '教辅'
    assert questions[0]['attribute_sources']['source_nature'] == 'paper'


def test_grade_semester_year_are_normalized():
    assert enums.normalize_grade('高一') == ('g10', True)
    assert enums.normalize_grade('七年级') == ('g7', True)
    assert enums.normalize_grade('g12') == ('g12', False)
    assert enums.normalize_semester('上学期') == ('1', True)
    assert enums.normalize_semester('2') == ('2', False)
    assert enums.normalize_year('2024年') == ('2024', True)
    assert enums.normalize_year('2024') == ('2024', False)

    paper = {'id': 'p1', 'paper_type': '期末',
             'attributes': {'grade': '高一', 'semester': '上学期', 'year': '2024年'}}
    core.normalize_paper(paper)
    assert paper['attributes']['grade'] == 'g10'
    assert paper['attributes']['semester'] == '1'
    assert paper['attributes']['year'] == '2024'
    assert any('年级' in message for message in paper['issues'])



def test_ability_values_are_per_subject():
    import abilities

    math = abilities.abilities('senior-math')
    chinese = abilities.abilities('senior-chinese')
    assert any(item['code'] == 'MA-SEN-LOG' for item in math)
    assert not any(item['code'] == 'MA-SEN-LOG' for item in chinese)
    assert len(abilities.levels()) == 4
    block = abilities.prompt_block('senior-math')
    assert 'MA-SEN-LOG' in block and 'C4' in block


def test_ability_result_rejects_cross_subject_code():
    import abilities

    result = abilities.normalize_result(
        {'ability': {'primary': 'CN-SEN-THINK', 'cognitive_level': 'C9'}}, 'senior-math')
    assert result == {'primary': None, 'secondary': None, 'cognitive_level': None}

    ok = abilities.normalize_result(
        {'ability': {'primary': 'MA-SEN-LOG', 'secondary': 'MA-SEN-ABS',
                     'cognitive_level': 'c4'}}, 'senior-math')
    assert ok == {'primary': 'MA-SEN-LOG', 'secondary': 'MA-SEN-ABS',
                  'cognitive_level': 'C4'}


def test_quality_level_is_normalized():
    paper = {'id': 'p1', 'paper_type': '期末',
             'attributes': {}, 'manual': {'quality_level': 'normal'}}
    core.normalize_paper(paper)
    assert paper['manual']['quality_level'] == '普通'
    bad = {'id': 'p2', 'paper_type': '期末', 'attributes': {},
           'manual': {'quality_level': 'excellent'}}
    core.normalize_paper(bad)
    assert bad['manual']['quality_level'] == ''


def test_legacy_difficulty_band_is_cleared():
    question = {'stem': 'x', 'subquestions': [],
                'attributes': {'difficulty': 5}}
    core.apply_question_structure_tags(question)
    assert question['attributes']['difficulty'] is None
    assert question['attributes']['difficulty_band'] == '困难'
    assert any('难度值超过 1' in item for item in question['issues'])

    normal = {'stem': 'x', 'subquestions': [], 'attributes': {'difficulty': 0.32}}
    core.apply_question_structure_tags(normal)
    assert normal['attributes']['difficulty'] == 0.32
    assert normal['attributes']['difficulty_band'] == '困难'


def test_unknown_source_is_cleared(monkeypatch):
    monkeypatch.setattr(core, 'source_names', lambda: {'金榜学案': '教辅'})
    monkeypatch.setattr(core, 'default_source',
                        lambda: {'name': '金榜学案', 'nature': '教辅'})
    paper = {'id': 'p1', 'paper_type': '期末',
             'attributes': {'source_name': '高中同步辅导与检测·数学'}}
    core.normalize_paper(paper)
    assert paper['attributes']['source_name'] == '金榜学案'
    assert any('不在来源字典内' in item for item in paper['issues'])


def test_grading_method_legacy_auto_maps_to_program():
    assert enums.normalize_grading_method('auto') == 'program'
    assert enums.normalize_grading_method('manual') == 'ai'
    assert enums.normalize_grading_method('program') == 'program'


def test_rubrics_skip_program_questions(monkeypatch):
    class NoCall:
        calls = []

        def json(self, *args, **kwargs):
            raise AssertionError('程序可批的题不应该调用评分标准')

    program = {'id': 'q1', 'paper_id': 'p1', 'number': '1', 'stem': 'x',
               'attributes': {'grading_method': 'program'}}
    core.apply_rubrics([program], [{'id': 'p1', 'title': '卷'}], NoCall())
    assert program.get('scoring') in (None, {})


def test_issue_append_is_deduplicated():
    question = {'issues': ['难度值超过 1，已按旧档位清空，请重新评估']}
    core.add_issue(question, '难度值超过 1，已按旧档位清空，请重新评估')
    core.add_issue(question, '别的提示')
    assert question['issues'] == ['难度值超过 1，已按旧档位清空，请重新评估', '别的提示']


def test_provider_errors_are_classified():
    import httpx
    from diagnostics import describe_error

    def make(status):
        request = httpx.Request('POST', 'https://api.deepseek.com/chat/completions')
        response = httpx.Response(status, request=request, json={'error': {'message': 'x'}})
        return httpx.HTTPStatusError('boom', request=request, response=response)

    balance = describe_error(make(402), service='llm')
    assert balance['retryable'] is False
    assert '余额不足' in balance['hint']

    early = describe_error(make(425), service='llm')
    assert early['retryable'] is True

    assert describe_error(make(429), service='llm')['retryable'] is True



