import grpc  # Added import
from concurrent import futures
import requests
from bs4 import BeautifulSoup
import tool_pb2
import tool_pb2_grpc
from grpc_reflection.v1alpha import reflection


class ToolServiceServicer(tool_pb2_grpc.ToolServiceServicer):
    def CallTool(self, request, context):
        tool = request.tool_name
        params = request.params
        result = tool_pb2.ToolResponse(success=False)
        try:
            if tool == "web_scrape":
                url = params.fields["url"].string_value if "url" in params.fields else ""
                if not url:
                    raise ValueError("URL not provided")
                resp = requests.get(url, timeout=5)
                soup = BeautifulSoup(resp.text, 'lxml')
                text = soup.get_text(separator="\n")
                result.success = True
                result.output = text[:10000]
            else:
                result.output = f"Tool '{tool}' not recognized."
            return result
        except Exception as e:
            result.success = False
            result.output = str(e)
            return result

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    tool_pb2_grpc.add_ToolServiceServicer_to_server(ToolServiceServicer(), server)

        # Enable reflection for ToolService
    service_names = (
        tool_pb2.DESCRIPTOR.services_by_name['ToolService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)
    
    server.add_insecure_port("[::]:50053")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
