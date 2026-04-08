import sys, os
# ensure project root is on sys.path when running as a script
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from frame.core.logging_config import setup_logging
from frame.core.config import AgentConfig, LLMConfig
from frame.core.llm import LLMClient
from frame.tool.registry import ToolRegistry
from frame.tool.todo import TODOTool
from frame.agent.todo_agent import TODOAgent
from frame.agent.processor_agent import TODOProcessorAgent
from frame.agent.summarizer_agent import TODOSummarizerAgent
from frame.agent.workflow_agent import WorkflowAgent
import os, json

# Enable stdout dump of split tasks
os.environ['WORKFLOW_DUMP_SPLIT_TO_STDOUT'] = '1'

setup_logging()
cfg = AgentConfig.from_env()
llm_cfg = LLMConfig.from_env()
llm = LLMClient(llm_cfg)
reg = ToolRegistry()
todo = TODOTool()
reg.register(todo)

# instantiate agents with shared registry
todo_agent = TODOAgent('TODOAgent', cfg, llm, tool_registry=reg)
proc_agent = TODOProcessorAgent('Processor', cfg, llm, tool_registry=reg)
sum_agent = TODOSummarizerAgent('Summarizer', cfg, llm, tool_registry=reg)

wf = WorkflowAgent('Workflow', cfg, llm, tool_registry=reg, todo_agent=todo_agent, processor_agent=proc_agent, summarizer_agent=sum_agent)
wf.build()

prompt = '请使用中文给我介绍一下什么是LLM'
print('RUNNING WORKFLOW...')
out = wf.think(prompt)
print('\n--- SUMMARY OUTPUT ---')
print(out)

backend = getattr(todo, '_backend', None)
print('\nbackend path:', getattr(backend, 'path', None))
try:
    if backend is not None and hasattr(backend, 'path'):
        with open(getattr(backend, 'path'), 'r', encoding='utf-8') as f:
            print('\n--- TODO JSON ---\n')
            print(f.read())

        log_file = os.path.join(os.path.dirname(getattr(backend, 'path')), 'workflow_debug.log')
        print('\n--- LOG FILE ---\n')
        try:
            with open(log_file, 'r', encoding='utf-8') as lf:
                print(lf.read())
        except Exception as e:
            print('cannot read log file:', e)
except Exception as e:
    print('cannot read todo json:', e)
