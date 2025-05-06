# app/retriever.py
import os
import logging
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import CharacterTextSplitter
import streamlit as st
from app.vector_db import VectorDB
from sentence_transformers import SentenceTransformer

load_dotenv()

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize FAQ vector store (only once)
def initialize_faq_vectorstore():
    if "faq_vectorstore" not in st.session_state:
        logger.info("Starting FAQ vector store initialization...")
        try:
            faq_file = "data/company_faq.txt"
            logger.info(f"Checking if FAQ file exists at: {os.path.abspath(faq_file)}")

            if not os.path.exists(faq_file):
                raise FileNotFoundError(f"FAQ file not found at {faq_file}")
            
            # Load the FAQ document
            logger.info("Loading FAQ file...")
            loader = TextLoader(faq_file)
            docs = loader.load()
            if not docs or not docs[0].page_content.strip():
                raise ValueError("FAQ file is empty or contains only whitespace")
            
            logger.info("Loaded FAQ document: %s", docs[0].page_content[:100] + "..." if len(docs[0].page_content) > 100 else docs[0].page_content)
            
            # Split the document
            logger.info("Splitting FAQ document...")
            text_splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
            split_docs = text_splitter.split_documents(docs)
            if not split_docs:
                raise ValueError("No document chunks created after splitting")
            logger.info("Split FAQ documents: %s", [doc.page_content[:100] + "..." if len(doc.page_content) > 100 else doc.page_content for doc in split_docs])
            
            # Initialize embeddings
            logger.info("Initializing embeddings...")
            embeddings = HuggingFaceEmbeddings(
                model_name="all-MiniLM-L6-v2",
                model_kwargs={"device": "cpu"}
            )

            # Create FAISS vector store
            logger.info("Creating FAISS vector store...")
            st.session_state.faq_vectorstore = FAISS.from_documents(split_docs, embeddings)
            logger.info("FAQ vector store initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing FAQ vector store: {str(e)}")
            st.session_state.faq_vectorstore = None
            raise  # Raise the exception to see the full stack trace in the logs

def retrieve_relevant_chunks(query: str, n_results_csv=2, n_results_faq=2) -> str:
    """
    Retrieve relevant chunks from both the FAQ vector store and CSV vector database.
    
    Args:
        query: The user's input message
        n_results_csv: Number of relevant CSV chunks to return (default: 2)
        n_results_faq: Number of relevant FAQ chunks to return (default: 2)
    
    Returns:
        A formatted string containing combined context from FAQ and CSV
    """
    # Initialize FAQ vector store if not already done
    initialize_faq_vectorstore()
    
    # 1. Retrieve from FAQ (FAISS)
    faq_context = ""
    if "faq_vectorstore" in st.session_state and st.session_state.faq_vectorstore is not None:
        faq_results = st.session_state.faq_vectorstore.similarity_search(query, k=n_results_faq)
        faq_chunks = [doc.page_content for doc in faq_results]
        logger.info("Retrieved FAQ chunks for query '%s': %s", query, faq_chunks)
        faq_context = "FAQ Information:\n" + "\n".join(faq_chunks) if faq_chunks else "No relevant FAQ information found."
    else:
        faq_context = "FAQ Information: Not available (vector store not initialized)."
        logger.warning("FAQ retrieval failed: Vector store not initialized")
    
    # 2. Retrieve from CSV (ChromaDB)
    csv_context = ""
    if "vector_db" not in st.session_state:
        st.session_state.vector_db = VectorDB()
    
    vector_db = st.session_state.vector_db

    try:
        # Query the CSV vector database
        csv_results = vector_db.query_vector_db(query_text=query, n_results=n_results_csv)
        
        if csv_results and csv_results.get("documents") and csv_results["documents"][0]:
            documents = csv_results["documents"][0]
            metadatas = csv_results["metadatas"][0] if csv_results.get("metadatas") else None
            
            context_lines = []
            for i, doc in enumerate(documents):
                line = f"Lead {i + 1}: {doc}"
                if metadatas and metadatas[i]:
                    metadata_str = " | ".join(f"{k}: {v}" for k, v in metadatas[i].items() if v)
                    if metadata_str:
                        line += f" ({metadata_str})"
                context_lines.append(line)
            
            csv_context = "Lead Information:\n" + "\n".join(context_lines)
            logger.info("Retrieved CSV chunks for query '%s': %s", query, documents)
        else:
            csv_context = "Lead Information: No relevant lead information found."
            logger.info("No CSV chunks retrieved for query '%s'", query)
    
    except Exception as e:
        csv_context = f"Lead Information: Error retrieving lead context: {str(e)}"
        logger.error("CSV retrieval error for query '%s': %s", query, str(e))
    
    # Combine both contexts
    combined_context = f"{faq_context}\n\n{csv_context}"
    return combined_context
