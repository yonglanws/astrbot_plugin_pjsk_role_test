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
    {"q": "在集体中，我希望成为大家关注的中心。"},
    {"q": "与朋友在一起时，我大部分时候会主动活跃气氛。"},
    {"q": "在陌生环境中，我会尝试尽快融入而不是观察一段时间。"},
    {"q": "我享受和少数密友的深度交流，但并不多于大型聚会。"},
    {"q": "当别人邀请我参加活动时，我通常会欣然接受。"},
    {"q": "在团队项目中，我倾向于和大家一起热烈讨论。"},
    {"q": "与初次见面的人交谈，对我来说不是太难的事。"},
    {"q": "我不会恐惧过于外向的人。"},
    {"q": "我会认为我属于乖孩子。"},
    {"q": "看到陌生人难过，我会产生想要安慰的冲动。"},
    {"q": "如果朋友真诚道歉，我愿意原谅的时候多于不原谅。"},
    {"q": "有时为了维持和谐，我会选择妥协，即便对我不公。"},
    {"q": "我相信大多数人是善意的。"},
    {"q": "当同学遇到困难，我乐于提供力所能及的帮助。"},
    {"q": "我讨厌冲突，会想办法避免争吵。"},
    {"q": "即使不同意别人的观点，我也会尝试尊重和理解。"},
    {"q": "我会为自己制定学习或生活计划，并尽量遵守。"},
    {"q": "我会坚持对自己热爱的事物，即便遇到他人反对。"},
    {"q": "我做事比较细心，会反复检查避免出错。"},
    {"q": "我对自己在意的事情标准比较高。"},
    {"q": "没有外部监督时，我也能自觉完成任务。"},
    {"q": "一旦开始一个任务，我通常会坚持到完成。"},
    {"q": "即便运气很差，我也会不断尝试。"},
    {"q": "我会认真对待自己的职责，无论是学习还是社团。"},
    {"q": "面临重要考试或活动前，我会感到过于紧张。"},
    {"q": "如果某件事没做好，我可能会懊恼很长时间。"},
    {"q": "我有时会担心未来可能发生的困难。"},
    {"q": "我的情绪会随着周围事情的好坏而波动。"},
    {"q": "我喜欢对同伴进行有效的建议，即便可能被视为压力。"},
    {"q": "做完选择后，经常会想如果选另一个会怎样。"},
    {"q": "我对别人的评价十分敏感，会在意很久。"},
    {"q": "在放松的时候，我不能够专注下来干某件事超过1个小时。"},
    {"q": "我对新鲜事物总是充满好奇。"},
    {"q": "我喜欢音乐、绘画或文学等艺术形式。"},
    {"q": "我偶尔会冒出一些新奇的想法或创意。"},
    {"q": "我愿意尝试没吃过的食物或没玩过的运动。"},
    {"q": "我喜欢思考一些抽象或哲学性的问题。"},
    {"q": "我对某类事物有偏爱，但并不狭隘。"},
    {"q": "即使不认同别人的看法，我也愿意倾听。"},
]

QUESTION_DIMS = [
    "EXT", "EXT", "EXT", "EXT", "EXT", "EXT", "EXT", "EXT",
    "AGR", "AGR", "AGR", "AGR", "AGR", "AGR", "AGR", "AGR",
    "CON", "CON", "CON", "CON", "CON", "CON", "CON", "CON",
    "NEU", "NEU", "NEU", "NEU", "NEU", "NEU", "NEU", "NEU",
    "OPN", "OPN", "OPN", "OPN", "OPN", "OPN", "OPN",
]

    # 逆向题索引（0-based）
    # EXT: 3 (不善社交), 7 (恐惧外向人)
    # AGR: 11 (不妥协), 14 (讨厌冲突-反向为喜欢冲突？不，14是"讨厌冲突，会想办法避免争吵"，正向是宜人，无逆向)
    # CON: 23 (放松时不能专注)
    # NEU: 27 (放松时不能专注-已归为CON), 31 (放松时不能专注-已归为CON)
    # OPN: 38 (即使不认同也倾听-正向)
    # 挑选出明确的逆向题：
    # 3: "我享受和少数密友的深度交流，但并不多于大型聚会。" -> 选5代表喜欢大型聚会，选1代表喜欢独处。这题其实是正向。
    # 7: "我不会恐惧过于外向的人。" -> 正向。
    # 31: "在放松的时候，我不能够专注下来干某件事超过1个小时。" -> 尽责性(CON)逆向题。
    # 38: "即使不认同别人的看法，我也愿意倾听。" -> 宜人性(AGR)或开放性(OPN)正向。
    # 重新审视题目，我们可以把以下题目设为逆向题：
    # 3 (第4题): "我享受和少数密友的深度交流，但并不多于大型聚会。" -> 设为逆向（选5代表外向低，即内向）
    # 31 (第32题): "在放松的时候，我不能够专注下来干某件事超过1个小时。" -> 尽责性逆向（选5代表尽责低）
QUESTION_REVERSE = {3, 31}

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

BATCH_SIZE = 10


class _SenderSessionFilter(SessionFilter):
    def filter(self, event: AstrMessageEvent) -> str:
        return f"{event.unified_msg_origin}:{event.get_sender_id()}"


def _parse_batch_answers(text: str, expected: int) -> list:
    nums = re.findall(r"[1-5]", text)
    return [int(n) for n in nums[:expected]]


def _build_batch_nodes(start_idx: int, questions_batch: list, bot_id: str) -> list:
    nodes = []
    for i, q in enumerate(questions_batch):
        q_num = start_idx + i + 1
        dim_name = DIM_LABELS.get(QUESTION_DIMS[start_idx + i], "")
        content = f"【第{q_num}题·{dim_name}】\n{q['q']}\n\n1=非常不同意 2=比较不同意 3=中立 4=比较同意 5=非常同意"
        nodes.append(Comp.Node(uin=bot_id, name="角色匹配测试", content=[Comp.Plain(content)]))
    return nodes


@register("pjsk_role_test", "DumChaer", "世界计划 角色匹配测试 - 通过39道题找到你在 Project Sekai 中的灵魂角色", "2.0.0")
class PjskGuessPersonaPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self._last_answer_at = {}
        self._session_locks = {}

    @filter.command("人格测试")
    async def start_test(self, event: AstrMessageEvent):
        if event.get_group_id():
            await self._run_group_test(event)
        else:
            await self._run_private_test(event)

    async def _run_group_test(self, event: AstrMessageEvent):
        bot_id = event.get_self_id()
        sender_id = event.get_sender_id()
        scores = {d: 0 for d in DIMS}
        current = 0
        total = len(QUESTIONS)
        session_key = f"{event.unified_msg_origin}:{sender_id}"
        sender_filter = _SenderSessionFilter()

        await event.send(event.plain_result(
            "世界计划人格测试\n"
            f"共{total}题，每{BATCH_SIZE}题一批发送。\n"
            "请用连续数字或逗号分隔作答，例如：1254324542 或 1,2,5,4,3,2,4,5,4,2\n"
            "发送 0 退出测试。"
        ))

        while current < total:
            batch_end = min(current + BATCH_SIZE, total)
            batch_questions = QUESTIONS[current:batch_end]
            batch_count = batch_end - current

            nodes = _build_batch_nodes(current, batch_questions, bot_id)
            batch_label = f"第{current // BATCH_SIZE + 1}批（第{current + 1}-{batch_end}题）"
            nodes.insert(0, Comp.Node(
                uin=bot_id, name="人格测试",
                content=[Comp.Plain(f"{batch_label}\n请回复{batch_count}个数字（1-5），如 1254324542")]
            ))
            await event.send(event.chain_result([Comp.Nodes(nodes)]))

            answered = False

            @session_waiter(timeout=180, record_history_chains=False)
            async def batch_waiter(controller: SessionController, ev: AstrMessageEvent):
                nonlocal current, scores, answered

                now_ts = time.time()
                last_ts = self._last_answer_at.get(session_key, 0)
                if now_ts - last_ts < 0.8:
                    return

                lock = self._session_locks.setdefault(session_key, asyncio.Lock())
                if lock.locked():
                    return

                text = ev.message_str.strip()

                if text == "0":
                    await ev.send(ev.plain_result("已退出测试。"))
                    controller.stop()
                    return

                answers = _parse_batch_answers(text, batch_count)

                if len(answers) < batch_count:
                    await ev.send(ev.plain_result(
                        f"⚠️ 需要{batch_count}个答案，你输入了{len(answers)}个。请重新输入{batch_count}个数字（1-5）。"
                    ))
                    controller.keep(timeout=180, reset_timeout=True)
                    return

                self._last_answer_at[session_key] = now_ts

                async with lock:
                    for j, ans in enumerate(answers):
                        q_idx = current + j
                        dim = QUESTION_DIMS[q_idx]
                        val = ans
                        if q_idx in QUESTION_REVERSE:
                            val = 6 - val
                        scores[dim] += val

                current = batch_end
                answered = True
                controller.stop()

            try:
                await batch_waiter(event, session_filter=sender_filter)
            except TimeoutError:
                await event.send(event.plain_result("⏰ 答题超时，请重新开始测试。"))
                if session_key:
                    self._last_answer_at.pop(session_key, None)
                    self._session_locks.pop(session_key, None)
                event.stop_event()
                return
            except Exception as e:
                logger.error(f"pjsk group test error: {e}")
                await event.send(event.plain_result("发生错误，请重新开始测试。"))
                if session_key:
                    self._last_answer_at.pop(session_key, None)
                    self._session_locks.pop(session_key, None)
                event.stop_event()
                return

            if not answered:
                break

        if current >= total:
            await self._send_result(event, scores)

        if session_key:
            self._last_answer_at.pop(session_key, None)
            self._session_locks.pop(session_key, None)
        event.stop_event()

    async def _run_private_test(self, event: AstrMessageEvent):
        sender_id = event.get_sender_id()
        await event.send(event.plain_result("请发送 1-5 作答，1 代表非常不同意，5 代表非常同意，发送 0 退出测试。\n共39题，请认真作答。"))

        scores = {d: 0 for d in DIMS}
        current = 0
        session_key = f"{event.unified_msg_origin}:{sender_id}"
        sender_filter = _SenderSessionFilter()

        @session_waiter(timeout=120, record_history_chains=False)
        async def question_waiter(controller: SessionController, event: AstrMessageEvent):
            nonlocal current, scores

            now_ts = time.time()
            last_ts = self._last_answer_at.get(session_key, 0)
            if now_ts - last_ts < 0.8:
                return

            lock = self._session_locks.setdefault(session_key, asyncio.Lock())
            if lock.locked():
                return

            text = event.message_str.strip()

            if text == "0":
                await event.send(event.plain_result("已退出测试。"))
                controller.stop()
                return

            if text not in ("1", "2", "3", "4", "5"):
                controller.keep(timeout=120, reset_timeout=True)
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
            controller.keep(timeout=120, reset_timeout=True)

        q = QUESTIONS[0]
        opt_text = "1. 非常不同意\n2. 比较不同意\n3. 中立\n4. 比较同意\n5. 非常同意"
        await event.send(event.plain_result(f"(1/{len(QUESTIONS)}) {q['q']}\n{opt_text}"))

        try:
            await question_waiter(event, session_filter=sender_filter)
        except TimeoutError:
            await event.send(event.plain_result("⏰ 答题超时，请重新开始测试。"))
        except Exception as e:
            logger.error(f"pjsk test error: {e}")
            await event.send(event.plain_result("发生错误，请重新开始测试。"))
        finally:
            if session_key:
                self._last_answer_at.pop(session_key, None)
                self._session_locks.pop(session_key, None)
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

        sd_parts = []
        for d in DIMS:
            val = scores.get(d, 0)
            if val > 0:
                sd_parts.append(f"{DIM_LABELS[d]}:{val}")
        if sd_parts:
            lines.append("")
            lines.append("📊 性格维度：" + " ".join(sd_parts))

        return "\n".join(lines)
