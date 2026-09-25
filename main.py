import os
import math
import re
import time
import asyncio
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.utils.session_waiter import session_waiter, SessionController, SessionFilter
import astrbot.api.message_components as Comp
from .image_gen import generate_result_image

DIMS = ["EXT", "AGR", "CON", "NEU", "OPN"]

DIM_LABELS = {
    "EXT": "外向性",
    "AGR": "宜人性",
    "CON": "尽责性",
    "NEU": "神经质",
    "OPN": "开放性",
}

QUESTIONS = [
    {"q": "在集体活动或舞台上，我希望成为大家关注的焦点。"},
    {"q": "和朋友相处时，我通常是活跃气氛、让大家开心的人。"},
    {"q": "在陌生环境或舞台上，我愿意主动表现自己，而不是先观察。"},
    {"q": "比起热闹的聚会或演出，我更喜欢和几个亲密的朋友安静地相处。"},
    {"q": "看到别人情绪低落，我会发自内心地想要安慰他们。"},
    {"q": "即使朋友曾经伤害过我，只要真诚道歉，我愿意原谅并继续相处。"},
    {"q": "我愿意相信大多数人的善意，即使曾经有过不愉快的经历。"},
    {"q": "当身边的人陷入困境，我会尽我所能伸出援手。"},
    {"q": "我会为自己制定明确的目标和计划，并努力去执行。"},
    {"q": "我做事认真细致，会反复检查直到自己满意为止。"},
    {"q": "即使没有人在监督，我也能自觉完成自己该做的事情。"},
    {"q": "一旦下定决心开始做一件事，我会坚持到底，不轻言放弃。"},
    {"q": "在重要的表演或考试前，我会感到紧张甚至焦虑。"},
    {"q": "如果事情没有按预期发展，我会很长时间陷入自责和自我怀疑。"},
    {"q": "我经常担心未来会发生不好的事情，即使现在一切顺利。"},
    {"q": "我很在意别人对我的看法，负面的评价会让我困扰很长时间。"},
    {"q": "我对未知的事物充满好奇，喜欢探索新的可能性。"},
    {"q": "我喜欢音乐、绘画等艺术形式，愿意花时间去创作或欣赏。"},
    {"q": "我愿意尝试新的体验，比如从未接触过的食物或活动。"},
    {"q": "我喜欢思考人生的意义、梦想的价值等抽象而深刻的问题。"},
]

QUESTION_DIMS = [
    "EXT", "EXT", "EXT", "EXT",
    "AGR", "AGR", "AGR", "AGR",
    "CON", "CON", "CON", "CON",
    "NEU", "NEU", "NEU", "NEU",
    "OPN", "OPN", "OPN", "OPN",
]

# 逆向题索引（0-based）：第4题"比起热闹的聚会或演出，我更喜欢和几个亲密的朋友安静地相处。"
# 选高分代表偏好安静（内向），反向计分
QUESTION_REVERSE = {3}

CHARACTERS = [
    {
        "name": "星乃一歌", "unit": "Leo/need", "color": "#33AAEE", "img_id": "1",
        "match": {"EXT": 2, "AGR": 4, "CON": 4, "NEU": 3, "OPN": 4},
        "desc": "你像一歌一样外表冷酷、内心温柔，不善表达但默默关心朋友。",
    },
    {
        "name": "天马咲希", "unit": "Leo/need", "color": "#FFDD44", "img_id": "2",
        "match": {"EXT": 5, "AGR": 5, "CON": 3, "NEU": 2, "OPN": 4},
        "desc": "你像咲希一样天生的乐天派，用乐观的态度鼓励大家继续前进。",
    },
    {
        "name": "望月穗波", "unit": "Leo/need", "color": "#EE6666", "img_id": "3",
        "match": {"EXT": 2, "AGR": 5, "CON": 5, "NEU": 4, "OPN": 3},
        "desc": "你像穗波一样温柔坚强，从讨好型人格逐渐学会表达真实想法。",
    },
    {
        "name": "日野森志步", "unit": "Leo/need", "color": "#BBDD22", "img_id": "4",
        "match": {"EXT": 1, "AGR": 3, "CON": 5, "NEU": 3, "OPN": 3},
        "desc": "你像志步一样外冷内热，用冷漠的外表保护自己温柔的内心。",
    },
    {
        "name": "花里实乃理", "unit": "MORE MORE JUMP!", "color": "#FFCCAA", "img_id": "5",
        "match": {"EXT": 5, "AGR": 5, "CON": 4, "NEU": 3, "OPN": 3},
        "desc": "你像实乃理一样元气满满，无论遇到什么困难都会积极面对。",
    },
    {
        "name": "桐谷遥", "unit": "MORE MORE JUMP!", "color": "#99CCFF", "img_id": "6",
        "match": {"EXT": 3, "AGR": 4, "CON": 5, "NEU": 2, "OPN": 3},
        "desc": "你像遥一样理性冷静，在关键时刻保持清醒的头脑。",
    },
    {
        "name": "桃井爱莉", "unit": "MORE MORE JUMP!", "color": "#FF6699", "img_id": "7",
        "match": {"EXT": 4, "AGR": 4, "CON": 5, "NEU": 2, "OPN": 3},
        "desc": "你像爱莉一样自信坚定，有着强烈的责任感和使命感。",
    },
    {
        "name": "日野森雫", "unit": "MORE MORE JUMP!", "color": "#99EEDD", "img_id": "8",
        "match": {"EXT": 2, "AGR": 5, "CON": 4, "NEU": 2, "OPN": 4},
        "desc": "你像雫一样优雅内敛，善于观察，拥有治愈人心的歌声。",
    },
    {
        "name": "小豆泽心羽", "unit": "Vivid BAD SQUAD", "color": "#FF6699", "img_id": "9",
        "match": {"EXT": 1, "AGR": 4, "CON": 3, "NEU": 5, "OPN": 3},
        "desc": "你像心羽一样极度内向胆小，但拥有不为人知的音乐天赋。",
    },
    {
        "name": "白石杏", "unit": "Vivid BAD SQUAD", "color": "#00BBDD", "img_id": "10",
        "match": {"EXT": 5, "AGR": 4, "CON": 4, "NEU": 2, "OPN": 4},
        "desc": "你像杏一样直率果断，好胜心强，从不服输。",
    },
    {
        "name": "东云彰人", "unit": "Vivid BAD SQUAD", "color": "#FF7722", "img_id": "11",
        "match": {"EXT": 5, "AGR": 4, "CON": 3, "NEU": 2, "OPN": 4},
        "desc": "你像彰人一样外向活泼，充满创造力。",
    },
    {
        "name": "青柳冬弥", "unit": "Vivid BAD SQUAD", "color": "#0077DD", "img_id": "12",
        "match": {"EXT": 2, "AGR": 3, "CON": 5, "NEU": 3, "OPN": 4},
        "desc": "你像冬弥一样沉默寡言但意志坚强，内心世界丰富。",
    },
    {
        "name": "天马司", "unit": "Wonderlands×Showtime", "color": "#FFBB00", "img_id": "13",
        "match": {"EXT": 5, "AGR": 3, "CON": 4, "NEU": 2, "OPN": 5},
        "desc": "你像司一样极度自信，梦想成为世界第一的Showstar。",
    },
    {
        "name": "凤笑梦", "unit": "Wonderlands×Showtime", "color": "#FF66BB", "img_id": "14",
        "match": {"EXT": 5, "AGR": 5, "CON": 2, "NEU": 1, "OPN": 5},
        "desc": "你像笑梦一样天真烂漫，充满无限的想象力和好奇心。",
    },
    {
        "name": "草薙宁宁", "unit": "Wonderlands×Showtime", "color": "#33DD99", "img_id": "15",
        "match": {"EXT": 1, "AGR": 4, "CON": 5, "NEU": 3, "OPN": 4},
        "desc": "你像宁宁一样温柔害羞，喜欢在幕后默默工作。",
    },
    {
        "name": "神代类", "unit": "Wonderlands×Showtime", "color": "#BB88EE", "img_id": "16",
        "match": {"EXT": 3, "AGR": 2, "CON": 3, "NEU": 3, "OPN": 5},
        "desc": "你像类一样古怪神秘，脑子里充满奇思妙想的天才发明家。",
    },
    {
        "name": "宵崎奏", "unit": "25时，Nightcord见。", "color": "#BB6688", "img_id": "17",
        "match": {"EXT": 1, "AGR": 3, "CON": 5, "NEU": 5, "OPN": 5},
        "desc": "你像奏一样,内心充满矛盾痛苦，通过音乐寻找救赎。",
    },
    {
        "name": "朝比奈真冬", "unit": "25时，Nightcord见。", "color": "#8888CC", "img_id": "18",
        "match": {"EXT": 1, "AGR": 2, "CON": 5, "NEU": 5, "OPN": 3},
        "desc": "你像真冬一样,完美的表象下隐藏着空虚迷茫的灵魂。",
    },
    {
        "name": "东云绘名", "unit": "25时，Nightcord见。", "color": "#CCAA88", "img_id": "19",
        "match": {"EXT": 3, "AGR": 3, "CON": 3, "NEU": 5, "OPN": 4},
        "desc": "你像绘名一样,极度渴望被认可，在寻找自我的路上不断努力。",
    },
    {
        "name": "晓山瑞希", "unit": "25时，Nightcord见。", "color": "#DDAACC", "img_id": "20",
        "match": {"EXT": 4, "AGR": 5, "CON": 3, "NEU": 3, "OPN": 4},
        "desc": "你像瑞希一样,喜欢所有可爱事物，用纯真和善良感染周围。",
    },
]

DIM_COUNTS = {d: 0 for d in DIMS}
for d in QUESTION_DIMS:
    DIM_COUNTS[d] += 1

BATCH_SIZE = 5


class _SenderSessionFilter(SessionFilter):
    def filter(self, event: AstrMessageEvent) -> str:
        return f"{event.unified_msg_origin}:{event.get_sender_id()}"


# 表情（含按键表情 1️⃣）、CQ 码、unicode/HTML 转义中可能混入数字，
# 提取答案前先整体剔除；全角数字/逗号归一化为半角。
_NOISE_RE = re.compile(r"(\[CQ:[^\]]*\]|\\u[0-9a-fA-F]{4}|&#x?[0-9a-fA-F]+;)")
_KEYCAP_RE = re.compile(r"[0-9#*]\uFE0F?\u20E3")
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\U0001F1E6-\U0001F1FF"
    "\uFE0E\uFE0F\u200D\u20E3"
    "]+"
)
_FULLWIDTH_TRANS = str.maketrans("０１２３４５６７８９，", "0123456789,")


def _clean_answer_text(text: str) -> str:
    text = _NOISE_RE.sub("", text)
    text = _KEYCAP_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    return text.translate(_FULLWIDTH_TRANS).strip()


def _parse_batch_answers(text: str, expected: int) -> list:
    compact = re.sub(r"[,，、．.\s]+", "", _clean_answer_text(text))
    if not compact or not re.fullmatch(r"[1-5]+", compact):
        return []
    return [int(n) for n in compact[:expected]]


def _format_question(q_num: int, q: dict) -> str:
    return f"【第{q_num}题】\n{q['q']}\n\n1=非常不同意 2=比较不同意 3=中立 4=比较同意 5=非常同意"


def _build_batch_nodes(start_idx: int, questions_batch: list, bot_id: str) -> list:
    nodes = []
    for i, q in enumerate(questions_batch):
        nodes.append(Comp.Node(
            uin=bot_id, name="人格测试",
            content=[Comp.Plain(_format_question(start_idx + i + 1, q))],
        ))
    return nodes


@register("pjsk_role_test", "DumChaer", "世界计划 角色匹配测试 - 通过20道题找到你在 Project Sekai 中的灵魂角色", "2.2.0")
class PjskGuessPersonaPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self._last_answer_at = {}
        self._session_locks = {}
        # 会话代次：同一用户中途重新开始测试时递增，用于让被覆盖的旧 waiter 静默超时
        self._session_gen = {}

    def _bump_session_gen(self, session_key: str) -> int:
        gen = self._session_gen.get(session_key, 0) + 1
        self._session_gen[session_key] = gen
        return gen

    def _cleanup_session(self, session_key: str, gen: int):
        # 代次不匹配时不清理，避免误删新一轮测试的会话状态
        if self._session_gen.get(session_key) == gen:
            self._session_gen.pop(session_key, None)
            self._last_answer_at.pop(session_key, None)
            self._session_locks.pop(session_key, None)

    @filter.command("人格测试")
    async def start_test(self, event: AstrMessageEvent):
        platform = event.get_platform_name() or ""
        is_qq_official = "qq_official" in platform
        if event.get_group_id():
            # 官方机器人适配器注册的平台名为 qq_official / qq_official_webhook
            if is_qq_official:
                await event.send(event.plain_result(
                    "官方QQ机器人在群聊中不支持此功能，请私信使用。"
                ))
                event.stop_event()
                return
            await self._run_group_test(event)
        else:
            # 官方机器人被动回复窗口为5分钟，超时须留出提示消息的发送余量
            await self._run_private_test(event, timeout=280 if is_qq_official else 300)

    async def _run_group_test(self, event: AstrMessageEvent):
        bot_id = event.get_self_id()
        sender_id = event.get_sender_id()
        scores = {d: 0 for d in DIMS}
        current = 0
        total = len(QUESTIONS)
        session_key = f"{event.unified_msg_origin}:{sender_id}"
        sender_filter = _SenderSessionFilter()
        gen = self._bump_session_gen(session_key)
        # 合并转发消息仅 aiocqhttp（QQ 个人号）支持，其他平台降级为纯文本发送
        use_forward = (event.get_platform_name() or "") == "aiocqhttp"

        await event.send(event.plain_result(
            "世界计划人格测试\n"
            f"共{total}题，每{BATCH_SIZE}题一批发送。\n"
            "请用连续数字或逗号分隔作答，例如：12543 或 1,2,5,4,3\n"
            "发送 0 退出测试，5分钟内未作答将自动结束。"
        ))

        while current < total:
            batch_end = min(current + BATCH_SIZE, total)
            batch_questions = QUESTIONS[current:batch_end]
            batch_count = batch_end - current
            batch_label = f"第{current // BATCH_SIZE + 1}批（第{current + 1}-{batch_end}题）"
            batch_hint = f"{batch_label}\n请回复{batch_count}个数字（1-5），如 12543"

            try:
                if use_forward:
                    nodes = _build_batch_nodes(current, batch_questions, bot_id)
                    nodes.insert(0, Comp.Node(
                        uin=bot_id, name="人格测试",
                        content=[Comp.Plain(batch_hint)]
                    ))
                    await event.send(event.chain_result([Comp.Nodes(nodes)]))
                else:
                    body = "\n\n".join(
                        _format_question(current + i + 1, q)
                        for i, q in enumerate(batch_questions)
                    )
                    await event.send(event.plain_result(f"{batch_hint}\n\n{body}"))
            except Exception as e:
                logger.error(f"pjsk group test send error: {e}")
                await event.send(event.plain_result("题目发送失败，请重新开始测试。"))
                self._cleanup_session(session_key, gen)
                event.stop_event()
                return

            answered = False

            @session_waiter(timeout=300, record_history_chains=False)
            async def batch_waiter(controller: SessionController, ev: AstrMessageEvent):
                nonlocal current, scores, answered

                now_ts = time.time()
                last_ts = self._last_answer_at.get(session_key, 0)
                if now_ts - last_ts < 0.8:
                    return

                text = _clean_answer_text(ev.message_str)

                if text == "0":
                    await ev.send(ev.plain_result("已退出测试。"))
                    controller.stop()
                    return

                answers = _parse_batch_answers(text, batch_count)

                if len(answers) < batch_count:
                    controller.keep(timeout=300, reset_timeout=True)
                    return

                self._last_answer_at[session_key] = now_ts

                # 计分为纯同步操作，asyncio 单线程下天然原子，无需加锁
                for j, ans in enumerate(answers):
                    q_idx = current + j
                    dim = QUESTION_DIMS[q_idx]
                    val = 6 - ans if q_idx in QUESTION_REVERSE else ans
                    scores[dim] += val

                current = batch_end
                answered = True
                controller.stop()

            try:
                await batch_waiter(event, session_filter=sender_filter)
            except TimeoutError:
                # 代次不匹配说明已有新一轮测试接管该会话，旧 waiter 的超时不应打扰用户
                if self._session_gen.get(session_key) == gen:
                    await event.send(event.plain_result("⏰ 超过5分钟未作答，测试已自动结束，请重新开始。"))
                self._cleanup_session(session_key, gen)
                event.stop_event()
                return
            except Exception as e:
                logger.error(f"pjsk group test error: {e}")
                if self._session_gen.get(session_key) == gen:
                    await event.send(event.plain_result("发生错误，请重新开始测试。"))
                self._cleanup_session(session_key, gen)
                event.stop_event()
                return

            if not answered:
                break

        if current >= total:
            await self._send_result(event, scores)

        self._cleanup_session(session_key, gen)
        event.stop_event()

    async def _run_private_test(self, event: AstrMessageEvent, timeout: int = 300):
        sender_id = event.get_sender_id()
        await event.send(event.plain_result(f"请发送 1-5 作答，1 代表非常不同意，5 代表非常同意，发送 0 退出测试。\n共{len(QUESTIONS)}题，请认真作答，5分钟内未作答将自动结束。"))

        scores = {d: 0 for d in DIMS}
        current = 0
        session_key = f"{event.unified_msg_origin}:{sender_id}"
        sender_filter = _SenderSessionFilter()
        gen = self._bump_session_gen(session_key)

        @session_waiter(timeout=timeout, record_history_chains=False)
        async def question_waiter(controller: SessionController, event: AstrMessageEvent):
            nonlocal current, scores

            now_ts = time.time()
            last_ts = self._last_answer_at.get(session_key, 0)
            if now_ts - last_ts < 0.8:
                return

            # 锁在 await 发送期间持有，配合上面的 locked() 检查挡住并发的重复消息
            lock = self._session_locks.setdefault(session_key, asyncio.Lock())
            if lock.locked():
                return

            text = _clean_answer_text(event.message_str)

            if text == "0":
                await event.send(event.plain_result("已退出测试。"))
                controller.stop()
                return

            if text not in ("1", "2", "3", "4", "5"):
                controller.keep(timeout=timeout, reset_timeout=True)
                return

            answer_value = int(text)
            self._last_answer_at[session_key] = now_ts
            dim = QUESTION_DIMS[current]
            if current in QUESTION_REVERSE:
                answer_value = 6 - answer_value
            scores[dim] += answer_value

            current += 1

            if current >= len(QUESTIONS):
                async with lock:
                    await self._send_result(event, scores)
                controller.stop()
                return

            async with lock:
                q = QUESTIONS[current]
                opt_text = "1. 非常不同意\n2. 比较不同意\n3. 中立\n4. 比较同意\n5. 非常同意"
                progress = f"({current + 1}/{len(QUESTIONS)})"
                await event.send(event.plain_result(f"{progress} {q['q']}\n{opt_text}"))
            controller.keep(timeout=timeout, reset_timeout=True)

        q = QUESTIONS[0]
        opt_text = "1. 非常不同意\n2. 比较不同意\n3. 中立\n4. 比较同意\n5. 非常同意"
        await event.send(event.plain_result(f"(1/{len(QUESTIONS)}) {q['q']}\n{opt_text}"))

        try:
            await question_waiter(event, session_filter=sender_filter)
        except TimeoutError:
            # 代次不匹配说明已有新一轮测试接管该会话，旧 waiter 的超时不应打扰用户
            if self._session_gen.get(session_key) == gen:
                await event.send(event.plain_result("⏰ 超过5分钟未作答，测试已自动结束，请重新开始。"))
        except Exception as e:
            logger.error(f"pjsk test error: {e}")
            if self._session_gen.get(session_key) == gen:
                await event.send(event.plain_result("发生错误，请重新开始测试。"))
        finally:
            self._cleanup_session(session_key, gen)
            event.stop_event()

    async def _send_result(self, event: AstrMessageEvent, scores: dict):
        try:
            ranked = self._calculate_ranked(scores)
            top = ranked[0][1]

            user_avg = {}
            for d in DIMS:
                count = DIM_COUNTS[d]
                if count > 0:
                    val = scores.get(d, 0) / count
                    user_avg[d] = round(max(1.0, min(5.0, val)), 2)
                else:
                    user_avg[d] = 3.0

            img_path = generate_result_image(
                user_avg, top, ranked, self.plugin_dir,
            )
            chain = [
                Comp.Plain("测试完成！这是你的结果："),
                Comp.Image.fromFileSystem(img_path),
            ]
            await event.send(event.chain_result(chain))
        except Exception as e:
            logger.error(f"generate image error: {e}")
            result_text = self._text_result(scores)
            await event.send(event.plain_result(result_text))

    def _calculate_ranked(self, scores: dict) -> list:
        user_avg = {}
        for d in DIMS:
            count = DIM_COUNTS[d]
            if count > 0:
                val = scores.get(d, 0) / count
                # 中心化拉伸（以 3.0 为中心拉伸 1.5 倍，放大性格倾向）
                stretched = 3.0 + (val - 3.0) * 1.5
                user_avg[d] = max(1.0, min(5.0, stretched))
            else:
                user_avg[d] = 3

        # 建议一：余弦相似度（Cosine Similarity）
        # 计算公式：cos(A, B) = (A · B) / (||A|| * ||B||)
        # 为了更好地衡量性格起伏，我们使用“中心化余弦相似度”（即皮尔逊相关系数），将向量减去中立值 3.0
        user_vec = [user_avg[d] - 3.0 for d in DIMS]
        user_norm = math.sqrt(sum(x ** 2 for x in user_vec))

        ranked = []
        for c in CHARACTERS:
            char_vec = [c["match"][d] - 3.0 for d in DIMS]
            char_norm = math.sqrt(sum(x ** 2 for x in char_vec))

            # 边界处理：如果用户或角色向量模长为 0（即所有维度都是 3.0 中立）
            if user_norm == 0 or char_norm == 0:
                # 此时退化为计算欧氏距离
                dist = math.sqrt(sum((user_avg[d] - c["match"][d]) ** 2 for d in DIMS))
                max_dist = math.sqrt(5 * 16)
                percent = max(0, min(100, round(100 * (1 - dist / max_dist))))
            else:
                dot_product = sum(u * cv for u, cv in zip(user_vec, char_vec))
                cosine = dot_product / (user_norm * char_norm)
                # 将余弦值 [-1, 1] 映射到契合度百分比 [0, 100]
                # 映射公式：percent = (cosine + 1) / 2 * 100
                percent = max(0, min(100, round((cosine + 1) / 2 * 100)))

            ranked.append((percent, c))

        ranked.sort(key=lambda x: x[0], reverse=True)

        return ranked

    def _text_result(self, scores: dict) -> str:
        ranked = self._calculate_ranked(scores)
        top = ranked[0][1]
        top3 = ranked[:3]

        lines = [f"🎭 你的灵魂角色是：{top['name']}"]
        lines.append(f"📀 {top['unit']}")
        lines.append("")
        lines.append(top["desc"])
        lines.append("")
        lines.append("━━━ 契合度分析 ━━━")
        for i, (score, c) in enumerate(top3):
            medal = "🥇" if i == 0 else ("🥈" if i == 1 else "🥉")
            lines.append(f"{medal} {i+1}. {c['name']}  {score}%")
            lines.append(f"   {c['unit']}")

        lines.append("")
        avg_parts = [f"{DIM_LABELS[d]}:{scores.get(d, 0) / DIM_COUNTS[d]:.1f}" for d in DIMS]
        lines.append("📊 性格维度均分（1-5）：" + " ".join(avg_parts))

        return "\n".join(lines)
