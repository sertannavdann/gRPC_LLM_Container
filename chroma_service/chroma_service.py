# chroma_service.py
import grpc
import chromadb
from concurrent import futures
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from . import chroma_pb2
from . import chroma_pb2_grpc
import threading
import logging
from grpc_reflection.v1alpha import reflection
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chroma_service")

class ChromaService:
    def __init__(self):
        self.lock = threading.Lock()
        self.embedder = SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        # Simplified client initialization for latest Chroma
        self.client = chromadb.PersistentClient(path="/app/data")
        self.collection = self.client.get_or_create_collection(
            name="documents",
            embedding_function=self.embedder,
            metadata={"hnsw:space": "cosine"}
        )

class ChromaServiceServicer(chroma_pb2_grpc.ChromaServiceServicer):
    def __init__(self):
        self.chroma = ChromaService()

    def AddDocument(self, request, context):
        with self.chroma.lock:
            try:
                metadata = dict(request.document.metadata) if request.document.metadata else {}
                self.chroma.collection.add(
                    documents=[request.document.text],
                    ids=[request.document.id],
                    metadatas=[metadata]
                )
                return chroma_pb2.AddDocumentResponse(success=True)
            except Exception as e:
                logger.error(f"Document add failed: {str(e)}")
                context.abort(grpc.StatusCode.INTERNAL, f"Storage error: {str(e)}")

    def Query(self, request, context):
        try:
            results = self.chroma.collection.query(
                query_texts=[request.query_text],
                n_results=min(request.top_k, 20),
                include=["documents", "metadatas", "distances"]
            )
            response = chroma_pb2.QueryResponse()
            
            if not results['documents']:
                return response
                
            for doc, meta, dist in zip(results['documents'][0],
                                    results['metadatas'][0],
                                    results['distances'][0]):
                entry = response.results.add()
                entry.text = doc
                if meta:
                    entry.metadata.update(meta)
                entry.score = float(1 - dist)
            return response
        except Exception as e:
            logger.error(f"Query failed: {str(e)}")
            context.abort(grpc.StatusCode.INTERNAL, f"Query error: {str(e)}")

class HealthServicer(health_pb2_grpc.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    chroma_pb2_grpc.add_ChromaServiceServicer_to_server(ChromaServiceServicer(), server)
    health_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)
    
    reflection.enable_server_reflection([
        chroma_pb2.DESCRIPTOR.services_by_name['ChromaService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME
    ], server)
    
    server.add_insecure_port("[::]:50052")
    server.start()
    logger.info("ChromaDB Service running on port 50052")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()