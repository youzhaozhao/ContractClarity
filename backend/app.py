import os
import json
import uuid
import threading
import traceback
import sqlite3
import secrets
import time
import re
import random
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt as pyjwt

from dotenv import load_dotenv
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise ValueError("未配置 DEEPSEEK_API_KEY 环境变量，请检查 .env 文件")

# JWT 密钥 —— 生产环境请在 .env 中设置 JWT_SECRET
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
# 开发模式下在响应中返回 OTP（便于测试），生产环境设为 false
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"
ACCESS_TOKEN_HOURS  = int(os.getenv("ACCESS_TOKEN_HOURS",  "2"))   # 短效访问令牌
REFRESH_TOKEN_DAYS  = int(os.getenv("REFRESH_TOKEN_DAYS",  "30"))  # 长效刷新令牌
OTP_EXPIRE_SECONDS  = 300   # 验证码 5 分钟有效
OTP_MAX_ATTEMPTS    = 5     # 单次 OTP 最大验证尝试次数
OTP_RATE_LIMIT_SEC  = 60    # 同手机号重发间隔（秒）
DB_PATH = os.getenv("DB_PATH", "contractclarity.db")

# 内存中的 OTP 存储和 JWT 黑名单（生产环境建议改为 Redis）
_otp_store   = {}   # phone -> {code, expiry, attempts, issued_at}
_token_bl    = set() # 已注销的 JTI 集合
_store_lock  = threading.Lock()

# ==================== 数据库初始化 ====================
def get_db():
    """每个请求获取独立的 SQLite 连接（Flask g 对象）"""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def init_db():
    """创建所有数据表（幂等操作，安全重复执行）"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            phone         TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            nickname      TEXT,
            email         TEXT DEFAULT '',
            bio           TEXT DEFAULT '',
            plan          TEXT DEFAULT 'free',
            review_count  INTEGER DEFAULT 0,
            join_date     TEXT NOT NULL,
            notifications TEXT DEFAULT '{"emailNotif":true,"smsNotif":false,"weeklyReport":true,"riskAlert":true}',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS contracts (
            id            TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL,
            date          TEXT NOT NULL,
            category      TEXT,
            contract_type TEXT,
            risk_score    INTEGER DEFAULT 0,
            overall_risk  TEXT,
            summary       TEXT,
            jurisdiction  TEXT,
            issues        TEXT DEFAULT '[]',
            created_at    TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS favorites (
            user_id     TEXT NOT NULL,
            contract_id TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            PRIMARY KEY (user_id, contract_id),
            FOREIGN KEY (user_id)     REFERENCES users(id)     ON DELETE CASCADE,
            FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_contracts_user_id ON contracts(user_id);
        CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON favorites(user_id);
    """)
    conn.commit()
    conn.close()
    print("数据库初始化完成:", DB_PATH)


# ==================== JWT 工具函数 ====================
def _now_ts():
    return int(datetime.now(timezone.utc).timestamp())


def issue_access_token(user_id: str) -> str:
    jti = secrets.token_hex(16)
    payload = {
        "sub":  user_id,
        "jti":  jti,
        "type": "access",
        "iat":  _now_ts(),
        "exp":  _now_ts() + ACCESS_TOKEN_HOURS * 3600,
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")


def issue_refresh_token(user_id: str) -> str:
    jti = secrets.token_hex(16)
    payload = {
        "sub":  user_id,
        "jti":  jti,
        "type": "refresh",
        "iat":  _now_ts(),
        "exp":  _now_ts() + REFRESH_TOKEN_DAYS * 86400,
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_token(token: str, expected_type: str = "access"):
    """解码并验证 JWT；返回 payload 或抛出异常"""
    payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise pyjwt.InvalidTokenError("token type mismatch")
    with _store_lock:
        if payload.get("jti") in _token_bl:
            raise pyjwt.InvalidTokenError("token has been revoked")
    return payload


def revoke_token(token: str):
    """将 JTI 加入黑名单（注销时调用）"""
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        with _store_lock:
            _token_bl.add(payload.get("jti"))
    except Exception:
        pass


# ==================== 鉴权中间件 ====================
def require_auth(f):
    """路由装饰器：验证 Authorization: Bearer <token> 并把 user_id 注入 g.user_id"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "missing_token", "message": "需要登录"}), 401
        token = auth_header[7:]
        try:
            payload = verify_token(token, "access")
        except pyjwt.ExpiredSignatureError:
            return jsonify({"error": "token_expired", "message": "登录已过期，请刷新令牌"}), 401
        except pyjwt.InvalidTokenError as e:
            return jsonify({"error": "invalid_token", "message": str(e)}), 401
        g.user_id = payload["sub"]
        return f(*args, **kwargs)
    return decorated


# ==================== OTP 工具函数 ====================
def _otp_generate(phone: str) -> tuple[str, str]:
    """
    生成并存储 OTP。
    返回 (otp_code, dev_hint)：
      - 开发模式 dev_hint 包含明文 OTP 供测试；生产模式为空字符串。
    """
    now = _now_ts()
    with _store_lock:
        existing = _otp_store.get(phone)
        if existing and now - existing.get("issued_at", 0) < OTP_RATE_LIMIT_SEC:
            remaining = OTP_RATE_LIMIT_SEC - (now - existing["issued_at"])
            raise ValueError(f"发送过于频繁，请 {remaining} 秒后重试")
        code = f"{random.randint(0, 999999):06d}"
        _otp_store[phone] = {
            "code":      code,
            "expiry":    now + OTP_EXPIRE_SECONDS,
            "attempts":  0,
            "issued_at": now,
        }
    # 生产环境在此接入短信 SDK
    print(f"[OTP] phone={phone}  code={code}  (dev_mode={DEV_MODE})")
    dev_hint = code if DEV_MODE else ""
    return code, dev_hint


def _otp_verify(phone: str, code: str) -> bool:
    """校验 OTP；失败累计尝试次数；超限或过期时自动清除"""
    now = _now_ts()
    with _store_lock:
        record = _otp_store.get(phone)
        if not record:
            raise ValueError("验证码不存在或已过期，请重新获取")
        if now > record["expiry"]:
            del _otp_store[phone]
            raise ValueError("验证码已过期，请重新获取")
        record["attempts"] += 1
        if record["attempts"] > OTP_MAX_ATTEMPTS:
            del _otp_store[phone]
            raise ValueError("验证码错误次数过多，请重新获取")
        if record["code"] != code:
            remaining = OTP_MAX_ATTEMPTS - record["attempts"]
            raise ValueError(f"验证码错误，还可尝试 {remaining} 次")
        del _otp_store[phone]  # 验证成功后立即销毁
    return True


# ==================== 用户数据库操作 ====================
def _user_to_dict(row) -> dict:
    if not row:
        return None
    d = dict(row)
    d.pop("password_hash", None)  # 不向前端暴露密码哈希
    try:
        d["notifications"] = json.loads(d.get("notifications") or "{}")
    except Exception:
        d["notifications"] = {}
    return d


def _db_get_user_by_id(conn, user_id: str):
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _user_to_dict(row)


def _db_get_user_by_phone(conn, phone: str):
    row = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    return dict(row) if row else None  # 包含 password_hash，仅内部使用


def _db_create_user(conn, phone: str, password_hash=None, nickname=None) -> dict:
    now_str = datetime.now(timezone.utc).isoformat()
    uid = str(uuid.uuid4())
    nickname = nickname or (phone[:3] + "****" + phone[-4:])
    conn.execute(
        """INSERT INTO users (id, phone, password_hash, nickname, join_date, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?)""",
        (uid, phone, password_hash, nickname, now_str, now_str, now_str)
    )
    conn.commit()
    return _db_get_user_by_id(conn, uid)


app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=True
)

# 每个请求结束后关闭 DB 连接
@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# 初始化数据库
init_db()

tasks = {}

# ==================== 支持的语言列表 ====================
LANGUAGE_MAP = {
    'zh-CN': 'Simplified Chinese (简体中文)',
    'zh-TW': 'Traditional Chinese (繁體中文)',
    'en':    'English',
    'ja':    'Japanese (日本語)',
    'ko':    'Korean (한국어)',
    'fr':    'French (Français)',
    'de':    'German (Deutsch)',
    'es':    'Spanish (Español)',
    'pt':    'Portuguese (Português)',
    'ar':    'Arabic (العربية)',
    'ru':    'Russian (Русский)',
}

print("正在初始化 BAAI/bge-large-zh-v1.5 嵌入模型...")
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-large-zh-v1.5",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)


def get_vectordb(category):
    """
    获取指定分类的向量数据库
    :param category: 合同分类
    :return: Chroma向量库实例或None
    """
    target_path = os.path.join("./chroma_db", category)
    if not os.path.exists(target_path):
        print(f"提示: 分类库 {category} 不存在，尝试使用通用库...")
        return None
    return Chroma(
        persist_directory=target_path,
        embedding_function=embeddings
    )


def robust_json_cleaner(text):
    """
    鲁棒的JSON文本清理函数：提取{}包裹的内容，移除markdown标记
    :param text: 原始文本
    :return: 清理后的JSON字符串
    """
    try:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            content = text[start:end + 1]
            content = content.replace('```json', '').replace('```', '').strip()
            return content
        return text
    except Exception as e:
        print(f"JSON清理失败: {e}")
        return text


def make_llm(max_tokens=3000):
    """创建 LLM 实例"""
    return ChatOpenAI(
        model='deepseek-chat',
        openai_api_key=DEEPSEEK_API_KEY,
        openai_api_base="https://api.deepseek.com",
        max_tokens=max_tokens,
        temperature=0.2,
        model_kwargs={"response_format": {"type": "json_object"}}
    )


def run_deep_analysis(task_id, contract_text, category, language='zh-CN'):
    """
    执行合同深度分析（异步执行）
    :param task_id: 任务唯一标识
    :param contract_text: 合同文本内容
    :param category: 合同分类
    :param language: 输出语言代码
    """
    try:
        lang_name = LANGUAGE_MAP.get(language, 'Simplified Chinese (简体中文)')
        lang_instruction = (
            f"CRITICAL LANGUAGE REQUIREMENT: You MUST write ALL output text "
            f"(titles, summaries, explanations, JSON string values, everything) "
            f"in {lang_name}. Do NOT use any other language for the output values."
        )

        llm = make_llm(max_tokens=3000)

        # ────────── 阶段1: 风险审查（含法律依据）──────────
        tasks[task_id]["progress"] = "正在查阅权威法条并进行风险审查..."
        tasks[task_id]["stage"] = 1
        print(f"任务 {task_id}: 执行阶段 1 (专家级风险点审查)...")

        vectordb = get_vectordb(category)
        docs = vectordb.similarity_search(contract_text, k=6) if vectordb else []
        laws_context = "\n".join(
            [f"【参考法条{i + 1}】: {d.page_content}" for i, d in enumerate(docs)]
        )

        prompt_1 = f"""{lang_instruction}

你是一位拥有顶级事务所背景的资深法律合伙人，擅长从微小细节中洞察法律风险。

任务：深度审查【待审合同】，结合【{category}】领域的【法律依据】进行穿透式分析。
【参考法律依据】：{laws_context}
【待审合同内容】：{contract_text}

【要求】：
1. 识别隐藏陷阱、责任不对等、关键条款缺失等。必须极其专业深刻。并提供对应 lawReference（具体法律名称、条目、内容）。
2. 给出 riskScore (0-100)。
3. 数量：请仅识别【最核心、风险等级最高】的 5-7 个风险点，严禁超过 8 个。
4. clauseText 必须是合同原文中的完整、逐字摘录，不要改动任何字符。

请输出 JSON（所有字符串值使用 {lang_name}）：
{{
  "contractType": "合同类型",
  "jurisdiction": "管辖地",
  "overallRisk": "极高/高/中/低 (translated)",
  "riskScore": 整数,
  "summary": "一句客观全面的点评",
  "issues": [
    {{
      "id": 1,
      "severity": "极高/高/中/低 (translated)",
      "title": "风险标题",
      "clauseText": "逐字摘录合同原文（不要修改任何空格或换行）",
      "lawReference": "具体法律名称、条目、内容",
      "plainLanguage": ["大白话解释"],
      "problem": "深度风险剖析",
      "whatToDo": ["精准行动对策"],
      "alternative": "防御性修订建议（具体条款替换文字）"
    }}
  ]
}}"""

        res_1 = llm.invoke(prompt_1)
        data_1 = json.loads(robust_json_cleaner(res_1.content), strict=False)

        # ────────── 阶段2a: 长邮件生成 ──────────
        tasks[task_id]["progress"] = "正在生成详尽谈判邮件..."
        tasks[task_id]["stage"] = 2
        print(f"任务 {task_id}: 执行阶段 2a (正在生成 500 字以上的谈判邮件)...")
        issues_brief = json.dumps(data_1['issues'], ensure_ascii=False)

        prompt_2a = f"""{lang_instruction}

你是一位资深商务律师和谈判专家。基于以下法律风险点，起草一封商务谈判长邮件。
【风险点摘要】：{issues_brief}

【要求】：
1. 邮件内容 ("email")：必须极其详尽，对每个关键风险点进行专业化阐述，解释其对双方合作的潜在影响。
2. 格式：严格遵守商务邮件格式，分段清晰，使用专业辞令。
3. 字数：不少于 500 字，展现极高的专业度和诚意。
4. 严禁使用双引号，引用请用单引号。
5. talkTrack 话术要自然，不要假定对方姓氏。

请输出 JSON：
{{
  "strategy": "总体博弈方针简述",
  "email": "500字以上的详尽谈判邮件全文..."
}}"""

        res_2a = llm.invoke(prompt_2a)
        data_2a = json.loads(robust_json_cleaner(res_2a.content), strict=False)

        # ────────── 阶段2b: 多风格谈判策略生成 ──────────
        tasks[task_id]["progress"] = "正在生成多方案谈判话术..."
        tasks[task_id]["stage"] = 2
        print(f"任务 {task_id}: 执行阶段 2b (正在生成多方案话术)...")

        prompt_2b = f"""{lang_instruction}

基于以下法律风险点，设计多维度的口头谈判脚本和不同风格的应对方案。
【风险点摘要】：{issues_brief}

【话术要求】：
1. talkTrack：包含自然的开场白和 3 个核心说服理由。
2. styles：提供强硬、协商、妥协三种截然不同的完整博弈逻辑，注意分点分段。
3. 话术要自然，不要假定对方姓氏与性别。

请输出 JSON：
{{
  "talkTrack": {{
    "opening": "话术...",
    "reasons": ["理由1", "理由2", "理由3"]
  }},
  "styles": {{
    "aggressive": "强硬风格的具体论点和压力测试话术...",
    "consultative": "协商风格的共赢话术与修改方案...",
    "compromise": "妥协风格的底线保障与折中条件..."
  }}
}}"""

        res_2b = llm.invoke(prompt_2b)
        data_2b = json.loads(robust_json_cleaner(res_2b.content), strict=False)

        # ────────── 阶段3: 完整修订合同生成 ──────────
        tasks[task_id]["progress"] = "正在生成完整修订版合同..."
        tasks[task_id]["stage"] = 3
        print(f"任务 {task_id}: 执行阶段 3 (生成完整修订合同)...")

        llm_large = make_llm(max_tokens=4000)

        prompt_3 = f"""{lang_instruction}

你是一位精通合同起草的资深法律顾问。请基于【原始合同】和【已识别的风险点及修订建议】，
生成一份完整的修订版合同。

【原始合同】：
{contract_text}

【风险点及修订建议】：
{issues_brief}

【任务要求】：
1. 保留原合同的完整结构、条款编号和所有未涉及风险的条款原文。
2. 对每个风险条款，应用其对应的 "alternative"（修订建议）进行替换或补充。
3. 如有缺失的重要条款，在合适位置补充完整。
4. 修订处用 【修订】 标记开头，便于对照查看。
5. revisionNotes 列出每处修订的简要说明。
6. revisedContract 包含完整的修订后合同全文。

请输出 JSON：
{{
  "revisedContract": "完整修订合同全文（保留原始结构，修订处以【修订】标记）...",
  "revisionNotes": [
    {{
      "clauseRef": "条款编号或名称",
      "change": "修订说明"
    }}
  ],
  "revisionSummary": "本次修订的整体说明（100字以内）"
}}"""

        res_3 = llm_large.invoke(prompt_3)
        data_3 = json.loads(robust_json_cleaner(res_3.content), strict=False)

        # ────────── 合并最终结果 ──────────
        tasks[task_id]["progress"] = "正在整合分析报告..."
        tasks[task_id]["stage"] = 4
        final_result = data_1
        final_result['negotiation'] = {
            "strategy": data_2a['strategy'],
            "email": data_2a['email'],
            "talkTrack": data_2b['talkTrack'],
            "styles": data_2b['styles']
        }
        final_result['revisedContract'] = data_3.get('revisedContract', '')
        final_result['revisionNotes'] = data_3.get('revisionNotes', [])
        final_result['revisionSummary'] = data_3.get('revisionSummary', '')

        tasks[task_id] = {
            "status": "completed",
            "result": final_result,
            "progress": "分析完成！"
        }
        print(f"任务 {task_id}: 全流程专家审查已完成。")

    except Exception as e:
        error_detail = traceback.format_exc()
        print(f"任务 {task_id} 异常详情: {error_detail}")
        print(f"原始异常信息: {str(e)}")
        tasks[task_id] = {
            "status": "failed",
            "error": str(e),
            "error_detail": error_detail,
            "progress": "分析失败"
        }


@app.route('/analyze', methods=['POST'])
def analyze():
    """
    启动合同分析任务（异步）
    请求参数：{"text": "合同文本", "category": "合同分类", "language": "语言代码"}
    返回：{"task_id": "任务ID"}
    """
    try:
        data = request.json or {}
        contract_text = data.get('text', '').strip()
        category = data.get('category', '其他类')
        language = data.get('language', 'zh-CN')

        if language not in LANGUAGE_MAP:
            language = 'zh-CN'

        if not contract_text:
            return jsonify({"error": "无合同内容"}), 400

        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            "status": "processing",
            "stage": 0,
            "progress": f"正在初始化【{category}】分析任务..."
        }

        threading.Thread(
            target=run_deep_analysis,
            args=(task_id, contract_text, category, language),
            daemon=True
        ).start()

        return jsonify({"task_id": task_id})
    except Exception as e:
        return jsonify({"error": f"请求处理失败: {str(e)}"}), 500


@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    """
    查询任务状态
    路径参数：task_id
    返回：任务状态（processing/completed/failed）及结果/错误信息
    """
    task = tasks.get(task_id)
    if not task:
        return jsonify({"status": "not_found"}), 404
    if "progress" not in task:
        task["progress"] = "处理中..."
    return jsonify(task)


@app.route('/ocr-refine', methods=['POST'])
def ocr_refine():
    """
    AI 优化 OCR 提取的原始文本
    请求参数：{"text": "OCR原始文本", "language": "语言代码"}
    返回：{"refined": "优化后的文本"}
    """
    try:
        data = request.json or {}
        raw_text = data.get('text', '').strip()
        language = data.get('language', 'zh-CN')
        lang_name = LANGUAGE_MAP.get(language, 'Simplified Chinese (简体中文)')

        if not raw_text:
            return jsonify({"error": "无文本内容"}), 400

        llm = ChatOpenAI(
            model='deepseek-chat',
            openai_api_key=DEEPSEEK_API_KEY,
            openai_api_base="https://api.deepseek.com",
            max_tokens=4000,
            temperature=0.1,
        )

        prompt = f"""You are a professional document OCR correction expert.
The following text was extracted via OCR from a scanned contract/document image and may contain:
- Random line breaks in the middle of sentences
- Garbled characters or misrecognized characters
- Extra spaces, duplicate characters
- Merged words that should be separate
- Missing punctuation

Please clean and reconstruct this OCR-extracted text into properly formatted, readable contract text.
Preserve ALL original content and meaning — do NOT add, remove or alter any substantive contract terms.
Fix only formatting, obvious OCR errors, and text flow issues.
Output the refined text as plain text only (no JSON, no markdown).

Raw OCR text:
{raw_text}"""

        res = llm.invoke(prompt)
        refined = res.content.strip()
        return jsonify({"refined": refined})

    except Exception as e:
        return jsonify({"error": f"OCR优化失败: {str(e)}"}), 500


@app.route('/languages', methods=['GET'])
def get_languages():
    """返回支持的语言列表"""
    return jsonify(LANGUAGE_MAP)


# ╔══════════════════════════════════════════════════════════════╗
# ║                   企业级鉴权 API 路由                         ║
# ╚══════════════════════════════════════════════════════════════╝

@app.route('/auth/send-otp', methods=['POST'])
def auth_send_otp():
    """
    发送手机验证码
    Body: {"phone": "13800138000"}
    开发模式返回 {"message": "...", "dev_otp": "123456"}；
    生产模式只返回 {"message": "..."}（OTP 经短信发送，不出现在响应体）
    """
    data  = request.json or {}
    phone = str(data.get("phone", "")).strip()
    if not re.match(r'^1[3-9]\d{9}$', phone):
        return jsonify({"error": "invalid_phone", "message": "手机号格式不正确"}), 400
    try:
        _, dev_hint = _otp_generate(phone)
    except ValueError as e:
        return jsonify({"error": "rate_limited", "message": str(e)}), 429
    resp = {"message": f"验证码已发送至 {phone[:3]}****{phone[-4:]}，5分钟内有效"}
    if dev_hint:
        resp["dev_otp"] = dev_hint   # 仅开发模式
    return jsonify(resp)


@app.route('/auth/login-sms', methods=['POST'])
def auth_login_sms():
    """
    短信验证码登录（未注册自动注册）
    Body: {"phone": "...", "otp": "123456"}
    """
    data  = request.json or {}
    phone = str(data.get("phone", "")).strip()
    otp   = str(data.get("otp",   "")).strip()
    if not re.match(r'^1[3-9]\d{9}$', phone):
        return jsonify({"error": "invalid_phone", "message": "手机号格式不正确"}), 400
    try:
        _otp_verify(phone, otp)
    except ValueError as e:
        return jsonify({"error": "otp_error", "message": str(e)}), 401

    db   = get_db()
    row  = _db_get_user_by_phone(db, phone)
    if row:
        user = _user_to_dict(db.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone())
    else:
        user = _db_create_user(db, phone)

    return jsonify({
        "access_token":  issue_access_token(user["id"]),
        "refresh_token": issue_refresh_token(user["id"]),
        "token_type":    "Bearer",
        "expires_in":    ACCESS_TOKEN_HOURS * 3600,
        "user":          user,
    })


@app.route('/auth/login-pwd', methods=['POST'])
def auth_login_pwd():
    """
    账号密码登录
    Body: {"phone": "...", "password": "..."}
    """
    data     = request.json or {}
    phone    = str(data.get("phone",    "")).strip()
    password = str(data.get("password", "")).strip()
    if not phone or not password:
        return jsonify({"error": "missing_fields", "message": "手机号和密码不能为空"}), 400

    db  = get_db()
    row = _db_get_user_by_phone(db, phone)
    if not row:
        return jsonify({"error": "not_found", "message": "该手机号未注册"}), 404

    pw_hash = row.get("password_hash")
    if not pw_hash:
        return jsonify({"error": "no_password", "message": "该账号未设置密码，请使用验证码登录"}), 400
    if not bcrypt.checkpw(password.encode(), pw_hash.encode()):
        return jsonify({"error": "wrong_password", "message": "密码错误"}), 401

    user = _user_to_dict(db.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone())
    return jsonify({
        "access_token":  issue_access_token(user["id"]),
        "refresh_token": issue_refresh_token(user["id"]),
        "token_type":    "Bearer",
        "expires_in":    ACCESS_TOKEN_HOURS * 3600,
        "user":          user,
    })


@app.route('/auth/register', methods=['POST'])
def auth_register():
    """
    注册新账号（需验证码）
    Body: {"phone":"...","otp":"...","password":"...","nickname":"...（可选）"}
    """
    data     = request.json or {}
    phone    = str(data.get("phone",    "")).strip()
    otp      = str(data.get("otp",      "")).strip()
    password = str(data.get("password", "")).strip()
    nickname = str(data.get("nickname", "")).strip() or None

    if not re.match(r'^1[3-9]\d{9}$', phone):
        return jsonify({"error": "invalid_phone", "message": "手机号格式不正确"}), 400
    if len(password) < 6:
        return jsonify({"error": "weak_password", "message": "密码至少 6 位字符"}), 400

    try:
        _otp_verify(phone, otp)
    except ValueError as e:
        return jsonify({"error": "otp_error", "message": str(e)}), 401

    db = get_db()
    if _db_get_user_by_phone(db, phone):
        return jsonify({"error": "already_exists", "message": "该手机号已注册，请直接登录"}), 409

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user    = _db_create_user(db, phone, pw_hash, nickname)
    return jsonify({
        "access_token":  issue_access_token(user["id"]),
        "refresh_token": issue_refresh_token(user["id"]),
        "token_type":    "Bearer",
        "expires_in":    ACCESS_TOKEN_HOURS * 3600,
        "user":          user,
    }), 201


@app.route('/auth/refresh', methods=['POST'])
def auth_refresh():
    """
    用 refresh_token 换取新的 access_token
    Body: {"refresh_token": "..."}
    """
    data  = request.json or {}
    token = str(data.get("refresh_token", "")).strip()
    if not token:
        return jsonify({"error": "missing_token"}), 400
    try:
        payload = verify_token(token, "refresh")
    except pyjwt.ExpiredSignatureError:
        return jsonify({"error": "refresh_expired", "message": "刷新令牌已过期，请重新登录"}), 401
    except pyjwt.InvalidTokenError as e:
        return jsonify({"error": "invalid_token", "message": str(e)}), 401

    user_id = payload["sub"]
    db   = get_db()
    user = _db_get_user_by_id(db, user_id)
    if not user:
        return jsonify({"error": "user_not_found"}), 404

    # 吊销旧 refresh token，签发新 access + refresh 对
    revoke_token(token)
    return jsonify({
        "access_token":  issue_access_token(user_id),
        "refresh_token": issue_refresh_token(user_id),
        "token_type":    "Bearer",
        "expires_in":    ACCESS_TOKEN_HOURS * 3600,
    })


@app.route('/auth/me', methods=['GET'])
@require_auth
def auth_me():
    """返回当前登录用户信息"""
    db   = get_db()
    user = _db_get_user_by_id(db, g.user_id)
    if not user:
        return jsonify({"error": "user_not_found"}), 404
    return jsonify(user)


@app.route('/auth/logout', methods=['POST'])
@require_auth
def auth_logout():
    """注销当前 access token（加入黑名单）"""
    token = request.headers.get("Authorization", "")[7:]
    revoke_token(token)
    data = request.json or {}
    if rt := data.get("refresh_token"):
        revoke_token(rt)
    return jsonify({"message": "已安全退出登录"})


@app.route('/auth/profile', methods=['PUT'])
@require_auth
def auth_update_profile():
    """
    更新用户资料
    Body: {"nickname":"...","email":"...","bio":"..."}
    """
    data = request.json or {}
    allowed = {k: str(v)[:200] for k, v in data.items() if k in ("nickname", "email", "bio")}
    if not allowed:
        return jsonify({"error": "no_fields", "message": "无可更新字段"}), 400

    now_str = datetime.now(timezone.utc).isoformat()
    sets    = ", ".join(f"{k}=?" for k in allowed)
    values  = list(allowed.values()) + [now_str, g.user_id]
    db = get_db()
    db.execute(f"UPDATE users SET {sets}, updated_at=? WHERE id=?", values)
    db.commit()
    return jsonify(_db_get_user_by_id(db, g.user_id))


@app.route('/auth/change-password', methods=['PUT'])
@require_auth
def auth_change_password():
    """
    修改密码
    Body: {"old_password":"...（若已设置）","new_password":"..."}
    """
    data    = request.json or {}
    old_pwd = str(data.get("old_password", "")).strip()
    new_pwd = str(data.get("new_password", "")).strip()
    if len(new_pwd) < 6:
        return jsonify({"error": "weak_password", "message": "新密码至少 6 位字符"}), 400

    db  = get_db()
    row = db.execute("SELECT password_hash FROM users WHERE id=?", (g.user_id,)).fetchone()
    if not row:
        return jsonify({"error": "user_not_found"}), 404

    existing_hash = row["password_hash"]
    if existing_hash:
        if not old_pwd:
            return jsonify({"error": "old_required", "message": "请输入当前密码"}), 400
        if not bcrypt.checkpw(old_pwd.encode(), existing_hash.encode()):
            return jsonify({"error": "wrong_password", "message": "当前密码错误"}), 401

    new_hash = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
    now_str  = datetime.now(timezone.utc).isoformat()
    db.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
               (new_hash, now_str, g.user_id))
    db.commit()
    return jsonify({"message": "密码修改成功", "has_password": True})


@app.route('/auth/notifications', methods=['PUT'])
@require_auth
def auth_update_notifications():
    """
    更新通知偏好
    Body: {"emailNotif": true, "smsNotif": false, ...}
    """
    data    = request.json or {}
    allowed_keys = {"emailNotif", "smsNotif", "weeklyReport", "riskAlert"}
    notif   = {k: bool(v) for k, v in data.items() if k in allowed_keys}
    now_str = datetime.now(timezone.utc).isoformat()
    db = get_db()
    db.execute("UPDATE users SET notifications=?, updated_at=? WHERE id=?",
               (json.dumps(notif), now_str, g.user_id))
    db.commit()
    return jsonify({"message": "通知设置已保存", "notifications": notif})


@app.route('/auth/account', methods=['DELETE'])
@require_auth
def auth_delete_account():
    """注销账号（删除所有用户数据）"""
    db = get_db()
    db.execute("DELETE FROM users WHERE id=?", (g.user_id,))
    db.commit()
    token = request.headers.get("Authorization", "")[7:]
    revoke_token(token)
    return jsonify({"message": "账号已永久注销"})


# ── 合同历史记录 ──

@app.route('/auth/contracts', methods=['GET'])
@require_auth
def auth_list_contracts():
    """获取当前用户所有合同记录（最新在前）"""
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM contracts WHERE user_id=? ORDER BY date DESC LIMIT 200",
        (g.user_id,)
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["issues"] = json.loads(d.get("issues") or "[]")
        except Exception:
            d["issues"] = []
        result.append(d)
    return jsonify(result)


@app.route('/auth/contracts', methods=['POST'])
@require_auth
def auth_save_contract():
    """
    保存合同分析记录
    Body: {date, category, contract_type, risk_score, overall_risk, summary, jurisdiction, issues}
    """
    data    = request.json or {}
    cid     = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()
    db = get_db()
    db.execute(
        """INSERT INTO contracts
           (id, user_id, date, category, contract_type, risk_score,
            overall_risk, summary, jurisdiction, issues, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            cid, g.user_id,
            data.get("date", now_str),
            data.get("category", ""),
            data.get("contract_type", ""),
            int(data.get("risk_score", 0)),
            data.get("overall_risk", ""),
            data.get("summary", ""),
            data.get("jurisdiction", ""),
            json.dumps(data.get("issues", []), ensure_ascii=False),
            now_str,
        )
    )
    # 更新用户审查计数
    db.execute("UPDATE users SET review_count=review_count+1, updated_at=? WHERE id=?",
               (now_str, g.user_id))
    db.commit()
    return jsonify({"id": cid, "message": "记录已保存"}), 201


@app.route('/auth/contracts/<contract_id>', methods=['DELETE'])
@require_auth
def auth_delete_contract(contract_id):
    """删除指定合同记录"""
    db  = get_db()
    row = db.execute(
        "SELECT id FROM contracts WHERE id=? AND user_id=?",
        (contract_id, g.user_id)
    ).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404
    db.execute("DELETE FROM contracts WHERE id=?", (contract_id,))
    db.execute("UPDATE users SET review_count=MAX(0,review_count-1) WHERE id=?", (g.user_id,))
    db.commit()
    return jsonify({"message": "记录已删除"})


# ── 收藏 ──

@app.route('/auth/favorites', methods=['GET'])
@require_auth
def auth_list_favorites():
    """返回当前用户收藏的合同 ID 列表"""
    db   = get_db()
    rows = db.execute(
        "SELECT contract_id FROM favorites WHERE user_id=? ORDER BY created_at DESC",
        (g.user_id,)
    ).fetchall()
    return jsonify([r["contract_id"] for r in rows])


@app.route('/auth/favorites/<contract_id>', methods=['POST'])
@require_auth
def auth_add_favorite(contract_id):
    """收藏合同"""
    db  = get_db()
    now = datetime.now(timezone.utc).isoformat()
    try:
        db.execute(
            "INSERT OR IGNORE INTO favorites (user_id, contract_id, created_at) VALUES (?,?,?)",
            (g.user_id, contract_id, now)
        )
        db.commit()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"message": "已收藏"})


@app.route('/auth/favorites/<contract_id>', methods=['DELETE'])
@require_auth
def auth_remove_favorite(contract_id):
    """取消收藏"""
    db = get_db()
    db.execute("DELETE FROM favorites WHERE user_id=? AND contract_id=?",
               (g.user_id, contract_id))
    db.commit()
    return jsonify({"message": "已取消收藏"})


if __name__ == '__main__':
    print("正在启动对簿AI ContractClarity 专家审查引擎...")
    print("ContractClarity 后端已启动，分析模式已就绪。")
    app.run(port=5000, debug=False)
