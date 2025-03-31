import grpc
from concurrent import futures
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import chroma_pb2
import chroma_pb2_grpc

# Initialize the embedding model
embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

# Update the embedding function signature as required
def embedding_function(input):
    return embedder.encode(input).tolist()

client = chromadb.PersistentClient(path="/app/data")
collection = client.get_or_create_collection(
    name="documents",
    embedding_function=embedding_function
)

class ChromaServiceServicer(chroma_pb2_grpc.ChromaServiceServicer):
    def AddDocument(self, request, context):
        doc = request.document
        collection.add(documents=[doc.text], ids=[doc.id] if doc.id else None)
        return chroma_pb2.AddDocumentResponse(success=True)

    def Query(self, request, context):
        results = collection.query(query_texts=[request.query_text], n_results=request.top_k or 5)
        resp = chroma_pb2.QueryResponse()
        docs = results.get('documents', [[]])[0]
        ids = results.get('ids', [[]])[0]
        for i, text in enumerate(docs):
            d = resp.results.add()
            d.id = ids[i] if ids else ""
            d.text = text
        return resp

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    chroma_pb2_grpc.add_ChromaServiceServicer_to_server(ChromaServiceServicer(), server)
    server.add_insecure_port("[::]:50052")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
