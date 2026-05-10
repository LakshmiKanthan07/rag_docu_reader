import os
import sys
import asyncio

# Add the app directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'rag_docu_reader')))

from dotenv import load_dotenv
load_dotenv('rag_docu_reader/.env')

from app.services.vectorstore import get_embeddings, get_vectorstore

async def test_cloud_services():
    print("--- Testing HuggingFace Embeddings ---")
    try:
        embeddings = get_embeddings()
        text = "Hello world"
        vector = await asyncio.to_thread(embeddings.embed_query, text)
        print(f"✓ Embeddings successful! Vector length: {len(vector)}")
    except Exception as e:
        print(f"✗ Embeddings failed: {e}")

    print("\n--- Testing Supabase Connection ---")
    try:
        vectorstore = get_vectorstore()
        # Just try to connect, don't perform a search yet
        print("✓ Supabase VectorStore initialized.")
        
        print("\n--- Testing Retrieval ---")
        docs = await asyncio.to_thread(vectorstore.similarity_search, "test", k=1)
        print(f"✓ Retrieval successful! Found {len(docs)} docs.")
    except Exception as e:
        print(f"✗ Supabase/Retrieval failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_cloud_services())
