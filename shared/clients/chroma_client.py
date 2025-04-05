from .base_client import BaseClient
import chroma_pb2
import chroma_pb2_grpc
import logging
from google.protobuf.struct_pb2 import Struct

logger = logging.getLogger(__name__)

class ChromaClient(BaseClient):
    def __init__(self):
        super().__init__("chromadb_service", 50052)
        self.stub = chroma_pb2_grpc.ChromaServiceStub(self.channel)

    @BaseClient._retry_decorator()
    def add_document(self, document_id: str, text: str, metadata: dict = None) -> bool:
        """Add document with structured metadata handling"""
        try:
            struct_metadata = Struct()
            if metadata:
                struct_metadata.update(metadata)
            
            response = self.stub.AddDocument(
                chroma_pb2.AddDocumentRequest(
                    document=chroma_pb2.Document(
                        id=document_id,
                        text=text,
                        metadata=struct_metadata
                    )
                )
            )
            return response.success
        except grpc.RpcError as e:
            logger.error(f"Document addition failed: {e.details()}")
            return False

    @BaseClient._retry_decorator()
    def query(self, query_text: str, top_k: int = 3) -> list:
        """Safe query with result normalization"""
        try:
            response = self.stub.Query(
                chroma_pb2.QueryRequest(
                    query_text=query_text,
                    top_k=min(top_k, 20)  # Enforce max results
                )
            )
            return [
                {
                    "text": doc.text,
                    "metadata": dict(doc.metadata),
                    "score": doc.score
                }
                for doc in response.results
            ]
        except grpc.RpcError as e:
            logger.error(f"Vector query failed: {e.code().name}")
            return []