#llm_service.py
import grpc
import logging
from concurrent import futures
import json
from json.decoder import JSONDecodeError

from llama_cpp import Llama

try:
    from . import llm_pb2
    from . import llm_pb2_grpc
except ImportError:
    import llm_pb2
    import llm_pb2_grpc

# Import config (works in both package and script mode)
try:
    from .config import get_config
except ImportError:
    from config import get_config

from grpc_reflection.v1alpha import reflection
from functools import lru_cache
from grpc_health.v1 import health, health_pb2_grpc, health_pb2
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("llm_service")

# Load configuration
CONFIG = get_config()
CONFIG.log_config()

JSON_GRAMMAR = '''root ::= (object)
object ::= "{" members "}"
members ::= pair | pair "," members
pair ::= string ":" value
value ::= string | number | object | array | "true" | "false" | "null"
array ::= "[" elements "]"
elements ::= value | value "," elements
string ::= '"' characters '"'
characters ::= "" | character characters
character ::= [^"\\] | "\\" escape
escape ::= ["\\/bfnrt] | "u" hex hex hex hex
hex ::= [0-9a-fA-F]
number ::= integer fraction exponent
integer ::= digit | onenine digits | "-" digit | "-" onenine digits
digit ::= [0-9]
onenine ::= [1-9]
fraction ::= "" | "." digits
exponent ::= "" | "e" sign digits | "E" sign digits
                "max_tokens": min(max(1, request.max_tokens), 1024),
digits ::= digit | digit digits'''

class HealthServicer(health.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING
        )

@lru_cache(maxsize=1)
def load_model():
    """Load LLM model from configuration."""
    logger.info("Loading model from %s", CONFIG.model_path)
    return Llama(
        model_path=CONFIG.model_path,
        n_ctx=CONFIG.n_ctx,
        n_threads=CONFIG.n_threads,
        n_batch=CONFIG.n_batch,
        verbose=CONFIG.verbose
    )

class LLMServiceServicer(llm_pb2_grpc.LLMServiceServicer):
    def Generate(self, request, context):
        try:
            llm = load_model()
            gen_config = {
                "max_tokens": min(request.max_tokens, CONFIG.max_tokens),
                "temperature": max(0.1, min(request.temperature, 1.0)),
                "grammar": self._get_json_grammar() if request.response_format == "json" else None,
                "stream": True
            }
            
            # Generation loop with JSON validation
            output_buffer = ""
            json_valid = True
            for output in llm(request.prompt, **gen_config):
                token = output["choices"][0]["text"]
                output_buffer += token
                
                
                # Validate JSON incrementally
                if request.response_format == "json":
                    try:
                        json.loads(output_buffer)
                        json_valid = True
                    except JSONDecodeError:
                        json_valid = False
                    
                yield llm_pb2.GenerateResponse(
                    token=token,
                    is_final=False,
                    is_valid_json=json_valid
                )
                
            yield llm_pb2.GenerateResponse(
                token="",
                is_final=True,
                is_valid_json=json_valid
            )

        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            context.abort(
                grpc.StatusCode.INTERNAL,
                f"Generation error ({type(e).__name__}): {str(e)}"
            )

            logger.error("Generation failed", exc_info=True)

    def _get_json_grammar(self):
        """Define strict JSON grammar for LLM"""
        return '''
        root ::= object
        value ::= object | array | string | number | "true" | "false" | "null"
        object ::= "{" ( string ":" value ("," string ":" value)* )? "}"
        array ::= "[" ( value ("," value)* )? "]"
        string ::= "\"" ( [^"\\] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] ) )* "\""
        number ::= "-"? ( "0" | [1-9] [0-9]* ) ( "." [0-9]+ )? ( [eE] [-+]? [0-9]+ )?
        '''
    
def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=CONFIG.max_workers))
    llm_pb2_grpc.add_LLMServiceServicer_to_server(LLMServiceServicer(), server)
    health_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)
    
    reflection.enable_server_reflection([
        llm_pb2.DESCRIPTOR.services_by_name['LLMService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME
    ], server)
    
    server.add_insecure_port(f"{CONFIG.host}:{CONFIG.port}")
    logger.info(f"LLM Service operational on {CONFIG.host}:{CONFIG.port}")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()