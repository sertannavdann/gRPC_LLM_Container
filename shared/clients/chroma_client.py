from .base_client import BaseClient

# Try local import first (when used as a service), fall back to shared/generated
try:
    from chroma_service import chroma_pb2
    from chroma_service import chroma_pb2_grpc
except ModuleNotFoundError:
    try:
        # Import from shared/generated when running in agent_service container
        from shared.generated import chroma_pb2, chroma_pb2_grpc
    except ModuleNotFoundError:
        # Last resort: try relative import
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'generated'))
        import chroma_pb2
        import chroma_pb2_grpc

import grpc
from google.protobuf.struct_pb2 import Struct

class ChromaClient(BaseClient):
    def __init__(self):
        super().__init__("chroma_service", 50052)
        self.stub = chroma_pb2_grpc.ChromaServiceStub(self.channel)

    def add_document(self, document_id: str, text: str, metadata: dict = None) -> bool:
        """Add document with automatic retries"""
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
            self.logger.error(f"Document addition failed: {e.details()}")
            return False

    def query(self, query_text: str, top_k: int = 3) -> list:
        """Query with automatic retry and result normalization"""
        try:
            response = self.stub.Query(
                chroma_pb2.QueryRequest(
                    query_text=query_text,
                    top_k=min(top_k, 20)
                )
            )
            # Filter out low-score results and empty texts
            return [
                {
                    "text": doc.text,
                    "metadata": dict(doc.metadata),
                    "score": doc.score
                }
                for doc in response.results
                if doc.score > 0.2 and doc.text.strip()
            ][:top_k]  # Ensure we don't return more than requested
        except grpc.RpcError as e:
            self.logger.error(f"Vector query failed: {e.code().name}")
            return []