"""
Deterministic XML format detection for Claude responses.
Uses hierarchical rules instead of scoring for predictable results.
"""

import re
import logging
from typing import List, Optional, Dict, Tuple

logger = logging.getLogger(__name__)


class DeterministicXMLDetector:
    """Deterministic XML format detection without scoring."""
    
    # Primary triggers - if ANY match, XML format IS required
    DETERMINISTIC_XML_TRIGGERS = [
        # Explicit format instructions
        r'Tool uses are formatted using XML-style tags',
        r'You (?:must|should|will) (?:use|respond with|format using) (?:the )?XML',
        r'(?:wrap|format) your (?:entire )?response in (?:proper )?(?:tool )?XML tags',
        r'respond using (?:the )?<\w+> tool',
        r'Your response MUST use the XML tool format',
        r'use XML tags for your response',
        r'MUST respond using the EXACT XML format',
        r'(?:must|should) respond using XML format',
        r'respond (?:with|in|using) XML',
        
        # Tool definition patterns
        r'<tool_name>\w+</tool_name>',
        r'Available tools?:\s*(?:\n|\r\n)?(?:\s*[-*]\s*)?<\w+>',
        r'Tools available:\s*<\w+>',
        
        # Format enforcement patterns
        r'use (?:a|the) tool in your (?:previous )?response',
        r'retry with a tool use',
        r'CRITICAL - THIS IS MANDATORY:.*XML',
        r'Your ENTIRE response MUST be wrapped in proper TOOL XML tags',
    ]
    
    # Exclusion patterns - if ANY match, XML format is NOT required
    EXCLUSION_PATTERNS = [
        # Explicit non-XML instructions
        r'respond in (?:plain text|JSON|markdown)',
        r'(?:do not|don\'t) use XML',
        r'format as JSON',
        r'return JSON',
        r'output JSON',
        
        # Code/example contexts - XML within code blocks
        r'```[^`]*<\w+>.*</\w+>[^`]*```',
        r'    <\w+>.*</\w+>',  # 4-space indented code
        
        # Example indicators before XML
        r'(?:example|sample|demo|e\.g\.|for instance):\s*<\w+>',
        r'(?:here\'s|this is) (?:an? )?(?:example|sample).*<\w+>',
        
        # HTML document indicators
        r'<!DOCTYPE\s+html',
        r'<html[^>]*>.*</html>',
        r'<meta\s+charset=',
    ]
    
    # Secondary patterns that need context verification
    SECONDARY_PATTERNS = [
        # Action-oriented tool names
        r'<(attempt_completion|ask_followup_question|new_task)>',
        r'<(\w+_\w+)>',  # Compound names like tool_name
        
        # Tool usage instructions
        r'use the (\w+) tool',
        r'invoke the (\w+) tool',
        r'call the (\w+) tool',
    ]
    
    # Definite non-tool tags to filter out
    DEFINITE_NON_TOOLS = {
        # HTML tags
        'html', 'head', 'body', 'div', 'span', 'p', 'a', 'img', 'table', 
        'tr', 'td', 'th', 'ul', 'ol', 'li', 'br', 'hr', 'h1', 'h2', 'h3', 
        'h4', 'h5', 'h6', 'meta', 'link', 'script', 'style',
        
        # Common XML tags
        'root', 'node', 'item', 'element', 'data', 'config', 'settings',
        'xml', 'doc', 'document',
        
        # Documentation/structure tags
        'task', 'environment_details', 'file', 'path', 'content', 'description',
        'parameter', 'parameters', 'argument', 'arguments', 'value', 'type',
        'name', 'required', 'mode', 'message', 'result', 'response',
    }
    
    def __init__(self):
        # Pre-compile all patterns for efficiency
        self.primary_triggers = [
            re.compile(p, re.IGNORECASE) 
            for p in self.DETERMINISTIC_XML_TRIGGERS
        ]
        self.exclusion_rules = [
            re.compile(p, re.IGNORECASE | re.DOTALL) 
            for p in self.EXCLUSION_PATTERNS
        ]
        self.secondary_patterns = [
            re.compile(p, re.IGNORECASE) 
            for p in self.SECONDARY_PATTERNS
        ]
        
    def remove_code_blocks(self, text: str) -> str:
        """Remove code blocks from text to avoid false positives."""
        # Remove fenced code blocks
        text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
        
        # Remove indented code blocks (4+ spaces at start of line)
        lines = text.split('\n')
        filtered_lines = []
        in_code_block = False
        
        for line in lines:
            if line.startswith('    ') and line.strip():
                in_code_block = True
            elif not line.strip():
                # Empty line might end code block
                if in_code_block and filtered_lines and not filtered_lines[-1].startswith('    '):
                    in_code_block = False
                filtered_lines.append(line)
            else:
                in_code_block = False
                filtered_lines.append(line)
                
        return '\n'.join(filtered_lines)
    
    def has_instruction_context(self, text: str) -> bool:
        """Check if text has instructional context."""
        instruction_words = [
            r'\b(?:must|should|will|need to|have to)\b',
            r'\b(?:use|format|respond|wrap|structure)\b',
            r'\b(?:your response|your output|the response)\b',
        ]
        
        for pattern in instruction_words:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def has_xml_tool_history(self, messages: List[Dict]) -> bool:
        """Check if previous messages show XML tool usage."""
        if not messages:
            return False
            
        for msg in messages:
            content = ""
            if isinstance(msg, dict):
                content = msg.get("content", "")
            elif hasattr(msg, "content"):
                content = msg.content
                
            if isinstance(content, str):
                content_lower = content.lower()
                # Check for definitive XML tool patterns in history
                if any([
                    "<attempt_completion>" in content_lower,
                    "<ask_followup_question>" in content_lower,
                    "<new_task>" in content_lower,
                    "tool uses are formatted" in content_lower,
                    "[error] you did not use a tool" in content_lower,
                ]):
                    return True
        return False
    
    def is_continuation_context(self, prompt: str) -> bool:
        """Check if prompt suggests continuation of previous context."""
        continuation_patterns = [
            r'continue',
            r'go on',
            r'proceed',
            r'what\'s next',
            r'keep going',
            r'retry',
            r'try again',
            r'please (?:continue|proceed)',
        ]
        
        prompt_lower = prompt.lower()
        for pattern in continuation_patterns:
            if re.search(pattern, prompt_lower):
                return True
        return False
    
    def extract_definite_tool_names(self, prompt: str) -> List[str]:
        """Extract only definitively identified tool names."""
        tools = set()
        
        # 1. Extract from explicit tool definitions
        for match in re.finditer(r'<tool_name>(\w+)</tool_name>', prompt, re.IGNORECASE):
            tools.add(match.group(1))
        
        # 2. Extract from known action patterns
        for match in re.finditer(r'use the (\w+) tool', prompt, re.IGNORECASE):
            tool_name = match.group(1)
            if tool_name.lower() not in self.DEFINITE_NON_TOOLS:
                tools.add(tool_name)
        
        # 3. Extract from compound tool names (e.g., attempt_completion)
        for match in re.finditer(r'<(\w+_\w+)>', prompt):
            tool_name = match.group(1)
            if tool_name.lower() not in self.DEFINITE_NON_TOOLS:
                tools.add(tool_name)
        
        # 4. Extract from tool lists
        for match in re.finditer(r'(?:tools?|commands?):\s*(?:\n|\r\n)?(?:\s*[-*]\s*)?<(\w+)>', prompt, re.IGNORECASE):
            tool_name = match.group(1)
            if tool_name.lower() not in self.DEFINITE_NON_TOOLS:
                tools.add(tool_name)
        
        # 5. Look for specific known tools mentioned without tags
        known_tools = ['attempt_completion', 'ask_followup_question', 'new_task']
        for tool in known_tools:
            if tool in prompt.lower():
                tools.add(tool)
        
        return list(tools)
    
    def check_secondary_rules(self, prompt: str, messages: Optional[List[Dict]]) -> Tuple[bool, str]:
        """Check secondary rules that need context verification."""
        prompt_clean = self.remove_code_blocks(prompt)
        
        # Rule 1: Action-oriented XML tags with instructional context
        action_tags = []
        for pattern in self.secondary_patterns:
            matches = pattern.findall(prompt_clean)
            action_tags.extend(matches)
        
        if action_tags and self.has_instruction_context(prompt_clean):
            filtered_tags = [t for t in action_tags if t.lower() not in self.DEFINITE_NON_TOOLS]
            if filtered_tags:
                return True, f"Action-oriented tags with instruction context: {filtered_tags}"
        
        # Rule 2: Multiple tool-like tags in instructional context
        all_tags = re.findall(r'<(\w+)>', prompt_clean)
        tool_tags = [t for t in all_tags if t.lower() not in self.DEFINITE_NON_TOOLS]
        if len(tool_tags) >= 2 and self.has_instruction_context(prompt_clean):
            return True, f"Multiple tool tags with instruction context: {tool_tags}"
        
        # Rule 3: Previous XML usage + continuation request
        if messages and self.has_xml_tool_history(messages):
            if self.is_continuation_context(prompt):
                return True, "Previous XML tool usage with continuation context"
        
        return False, ""
    
    def detect(self, prompt: str, messages: Optional[List[Dict]] = None) -> Tuple[bool, str, List[str]]:
        """
        Deterministically detect if XML format is required.
        Returns (xml_required, reason, tool_names)
        """
        # Step 1: Check exclusion rules first (highest priority)
        for i, pattern in enumerate(self.exclusion_rules):
            if pattern.search(prompt):
                reason = f"Exclusion rule #{i+1}: {self.EXCLUSION_PATTERNS[i]}"
                logger.debug(f"XML Detection: NO - {reason}")
                return False, reason, []
        
        # Step 2: Check primary triggers (definitive XML required)
        for i, pattern in enumerate(self.primary_triggers):
            if pattern.search(prompt):
                reason = f"Primary trigger #{i+1}: {self.DETERMINISTIC_XML_TRIGGERS[i]}"
                tool_names = self.extract_definite_tool_names(prompt)
                logger.info(f"📋 XML Detection: YES - {reason}")
                if tool_names:
                    logger.info(f"   Detected tools: {', '.join(tool_names)}")
                return True, reason, tool_names
        
        # Step 3: Check secondary rules with context
        secondary_match, secondary_reason = self.check_secondary_rules(prompt, messages)
        if secondary_match:
            tool_names = self.extract_definite_tool_names(prompt)
            logger.info(f"📋 XML Detection: YES - {secondary_reason}")
            if tool_names:
                logger.info(f"   Detected tools: {', '.join(tool_names)}")
            return True, secondary_reason, tool_names
        
        # Default: No XML required
        logger.debug("XML Detection: NO - No deterministic indicators found")
        return False, "No XML format indicators found", []