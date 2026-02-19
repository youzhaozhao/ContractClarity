import os
import shutil

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

SOURCE_LAWS_DIR = './法律条文'
DB_BASE_DIR = './chroma_db'
LAW_CATEGORIES = [ 
    '劳动用工类',
    '房产物业类',
    '消费服务类',
    '金融借贷类',
    '网络数字类',
    '婚姻家庭类',
    '经营合作类',
    '其他类'
]

def load_text_documents(dir_path: str) -> list:
    """
    加载指定目录下的所有txt文本文档
    :param dir_path: 文档目录路径
    :return: 加载的文档列表（空列表表示加载失败/无文档）
    """
    if not os.path.exists(dir_path):
        return []
    
    try:
        loader = DirectoryLoader(
            dir_path,
            glob="**/*.txt",
            loader_cls=TextLoader,
            loader_kwargs={'encoding': 'utf-8'}
        )
        docs = loader.load()
        return docs
    except Exception as e:
        print(f"   × 加载目录 {dir_path} 文档失败: {str(e)}")
        return []

def safe_remove_dir(dir_path: str):
    """
    安全删除目录（处理权限/不存在等异常）
    :param dir_path: 待删除目录路径
    """
    if os.path.exists(dir_path):
        try:
            shutil.rmtree(dir_path)
            print(f"   - 已清理旧向量库目录: {dir_path}")
        except Exception as e:
            raise RuntimeError(f"删除目录 {dir_path} 失败（请检查权限）: {e}")

def process_all_categories():
    if not os.path.exists(SOURCE_LAWS_DIR):
        raise FileNotFoundError(f"核心目录不存在: {SOURCE_LAWS_DIR}，请确认法律条文文件已放置")
    
    print("正在初始化嵌入模型 (BAAI/bge-large-zh-v1.5)...")
    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-large-zh-v1.5",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )

    text_splitter = CharacterTextSplitter(chunk_size=600, chunk_overlap=60)

    for category in LAW_CATEGORIES:
        print(f"\n>>> 正在处理分类: 【{category}】")
        
        category_doc_path = os.path.join(SOURCE_LAWS_DIR, category)
        common_doc_path = os.path.join(SOURCE_LAWS_DIR, '通用')
        persist_dir = os.path.join(DB_BASE_DIR, category)

        safe_remove_dir(persist_dir)

        all_docs = []
        
        # 加载分类专属法条
        category_docs = load_text_documents(category_doc_path)
        all_docs.extend(category_docs)
        print(f"   - 已加载专属法条: {len(category_docs)} 个文档")

        # 加载通用法条
        common_docs = load_text_documents(common_doc_path)
        all_docs.extend(common_docs)
        print(f"   - 已集成通用法条: {len(common_docs)} 个文档")

        if not all_docs:
            print(f"   ! 警告: 分类 {category} 下未找到任何文档，跳过。")
            continue

        split_docs = text_splitter.split_documents(all_docs)
        print(f"   - 已切分为 {len(split_docs)} 个文本片段")

        try:
            print(f"   - 正在写入向量库到: {persist_dir}...")
            Chroma.from_documents(
                documents=split_docs,
                embedding=embeddings,
                persist_directory=persist_dir
            )
            print(f"√ 【{category}】向量库构建完成！")
        except Exception as e:
            print(f"   × 【{category}】向量库构建失败: {str(e)}")
            continue

    print("\n" + "="*30)
    print("所有分类法律向量库构建流程执行完毕！")
    print("="*30)

if __name__ == "__main__":
    try:
        process_all_categories()
    except Exception as e:
        print(f"\n程序执行失败: {str(e)}")
        exit(1)  