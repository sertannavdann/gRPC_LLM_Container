import grpc
import chromadb
from concurrent import futures
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
import chroma_pb2
import chroma_pb2_grpc
from grpc_reflection.v1alpha import reflection
import threading

class ChromaService:
    def __init__(self):
        self.lock = threading.Lock()
        self.embedder = SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
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
                self.chroma.collection.add(
                    documents=[request.document.text],
                    ids=[request.document.id],
                    metadatas=[{"source": request.document.source}]
                )
                return chroma_pb2.AddDocumentResponse(success=True)
            except Exception as e:
                context.abort(grpc.StatusCode.INTERNAL, f"Storage error: {str(e)}")

    def Query(self, request, context):
        try:
            results = self.chroma.collection.query(
                query_texts=[request.query_text],
                n_results=min(request.top_k, 20),
                include=["documents", "metadatas", "distances"]
            )
            response = chroma_pb2.QueryResponse()
            for doc, meta, dist in zip(results['documents'][0], 
                                      results['metadatas'][0], 
                                      results['distances'][0]):
                entry = response.results.add()
                entry.text = doc
                entry.metadata.update(meta)
                entry.score = float(1 - dist)  # Convert distance to similarity score
            return response
        except Exception as e:
            context.abort(grpc.StatusCode.INTERNAL, f"Query error: {str(e)}")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    chroma_pb2_grpc.add_ChromaServiceServicer_to_server(ChromaServiceServicer(), server)
    
    reflection.enable_server_reflection([
        chroma_pb2.DESCRIPTOR.services_by_name['ChromaService'].full_name,
        reflection.SERVICE_NAME
    ], server)
    
    server.add_insecure_port("[::]:50052")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()