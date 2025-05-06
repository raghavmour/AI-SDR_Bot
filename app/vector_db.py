# app/vector_db.py

import pandas as pd
import os
import PyPDF2
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain.docstore.document import Document
from langchain.text_splitter import CharacterTextSplitter

load_dotenv()

class VectorDB:
    def __init__(self):
        print("Initializing new FAISS-based VectorDB instance...")

        # Initialize embeddings
        self.embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"}
        )

        # Initialize an empty FAISS store
        self.vectorstore = None
        print("FAISS VectorDB initialized (empty)")

    def extract_chunks_from_csv(self, df):
        """Convert dataframe rows into text chunks."""
        return df.astype(str).apply(lambda x: " | ".join(x), axis=1).tolist()

    def extract_text_from_pdf(self, pdf_file):
        """Extract text from a PDF file."""
        try:
            reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text.strip()
        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            return ""

    def extract_text_from_txt(self, txt_file):
        """Extract text from a TXT file."""
        try:
            return txt_file.read().decode("utf-8").strip()
        except Exception as e:
            print(f"Error reading text from TXT: {e}")
            return ""

    def _split_text_into_documents(self, text_list, metadatas=None, chunk_size=1000, chunk_overlap=100):
        """Split text into smaller documents with optional metadata."""
        text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        documents = []

        for i, text in enumerate(text_list):
            splits = text_splitter.create_documents([text])
            for doc in splits:
                if metadatas and i < len(metadatas):
                    doc.metadata = metadatas[i]
                documents.append(doc)

        return documents

    def create_vector_db_from_csv(self, df, metadata_cols=None):
        """Create FAISS vectorstore from CSV dataframe."""
        chunks = self.extract_chunks_from_csv(df)

        metadatas = None
        if metadata_cols and all(col in df.columns for col in metadata_cols):
            metadatas = df[metadata_cols].to_dict('records')

        print("Splitting CSV data into documents...")
        documents = self._split_text_into_documents(chunks, metadatas=metadatas)

        if not documents:
            print("No documents created from CSV data")
            return False

        print("Creating FAISS vectorstore from CSV data...")
        self.vectorstore = FAISS.from_documents(documents, self.embeddings)
        print("FAISS vectorstore created from CSV data")
        return True

    def create_vector_db_from_text(self, text, source_name="text_file"):
        """Store text content in the vectorstore."""
        if not text:
            return False

        print("Splitting text into documents...")
        documents = self._split_text_into_documents([text])

        if not documents:
            print("No documents created from text")
            return False

        print(f"Creating FAISS vectorstore from {source_name} text...")
        self.vectorstore = FAISS.from_documents(documents, self.embeddings)
        print("FAISS vectorstore created from text data")
        return True

    def query_vector_db(self, query_text, n_results=2):
        """Query FAISS vectorstore."""
        if not self.vectorstore:
            print("Vectorstore is empty; nothing to query")
            return None

        print(f"Querying FAISS vectorstore for '{query_text}'...")
        results = self.vectorstore.similarity_search_with_score(query_text, k=n_results)

        documents = []
        metadatas = []
        for doc, score in results:
            documents.append(doc.page_content)
            metadatas.append(doc.metadata if doc.metadata else None)

        return {"documents": [documents], "metadatas": [metadatas]}

    def clear_collection(self):
        """Clear FAISS vectorstore (reset it)."""
        print("Clearing FAISS vectorstore...")
        self.vectorstore = None
        print("FAISS vectorstore cleared")

