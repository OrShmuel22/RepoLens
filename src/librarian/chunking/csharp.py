"""
C# language chunker implementation.
"""

import re
from typing import Dict, List, Optional

from .base import BaseChunker, ChunkData


# Patterns for C# semantic boundary detection
PATTERNS = {
    'namespace': re.compile(r'^namespace\s+([\w\.]+)'),
    'class': re.compile(r'^(?:public|private|internal|protected)?\s*(?:static|sealed|abstract|partial)?\s*(?:class|interface|struct|record|enum)\s+(\w+)'),
    'method': re.compile(r'^(?:public|private|protected|internal)?\s*(?:static|virtual|override|async|abstract)?\s*[\w<>\[\],\s]+\s+(\w+)\s*\([^)]*\)'),
    'property': re.compile(r'^(?:public|private|protected|internal)?\s*(?:static|virtual|override)?\s*[\w<>\[\],\s]+\s+(\w+)\s*{\s*(?:get|set)'),
}

# Architecture patterns for boosting in search results
ARCH_INDICATORS = [
    'IServiceCollection', 'IApplicationBuilder', 'IConfiguration',
    'builder.Services', 'app.Use', 'services.Add',
    '[ApiController]', '[HttpGet', '[HttpPost', '[HttpPut', '[HttpDelete',
    '[Route(', '[Authorize', 'DependencyInjection',
    'Startup', 'Program.cs', 'appsettings',
]


class CSharpChunker(BaseChunker):
    """
    C# semantic chunker that splits files at class/method boundaries.
    """
    
    @property
    def supported_extensions(self) -> List[str]:
        return ['.cs', '.csx']
    
    @property
    def language_name(self) -> str:
        return 'C#'
    
    def chunk_file(self, filepath: str, content: str) -> List[ChunkData]:
        """Chunk a C# file at semantic boundaries."""
        lines = content.splitlines()
        if not lines:
            return []
        
        structure = self._parse_structure(lines)
        
        if structure['methods'] or structure['properties']:
            chunks = self._chunk_by_members(filepath, lines, structure)
        else:
            chunks = self._chunk_by_lines(filepath, lines, structure)
        
        header_chunk = self._create_header_chunk(filepath, lines, structure)
        if header_chunk:
            chunks.insert(0, header_chunk)
        
        return chunks
    
    def _parse_structure(self, lines: List[str]) -> Dict:
        """Parse C# file structure to find semantic boundaries."""
        structure = {
            'namespace': None,
            'classes': [],
            'methods': [],
            'properties': [],
            'usings_end': 0,
        }
        
        brace_depth = 0
        current_class = None
        current_class_depth = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Track using statements
            if stripped.startswith('using ') and structure['usings_end'] == 0:
                structure['usings_end'] = i
            elif not stripped.startswith('using ') and not stripped.startswith('//') and stripped:
                if structure['usings_end'] == 0:
                    structure['usings_end'] = i
            
            # Namespace
            match = PATTERNS['namespace'].match(stripped)
            if match:
                structure['namespace'] = match.group(1)
            
            # Class/Interface/Struct
            match = PATTERNS['class'].match(stripped)
            if match:
                current_class = match.group(1)
                current_class_depth = brace_depth
                structure['classes'].append({
                    'name': current_class,
                    'start': i,
                    'end': None,
                    'depth': brace_depth
                })
            
            # Method
            if current_class and '(' in stripped and ')' in stripped:
                match = PATTERNS['method'].match(stripped)
                if match and not stripped.endswith(';'):
                    structure['methods'].append({
                        'name': match.group(1),
                        'start': i,
                        'end': None,
                        'class': current_class
                    })
            
            # Property
            match = PATTERNS['property'].match(stripped)
            if match and current_class:
                structure['properties'].append({
                    'name': match.group(1),
                    'start': i,
                    'end': None,
                    'class': current_class
                })
            
            # Track braces
            brace_depth += stripped.count('{') - stripped.count('}')
            
            # Close class
            if structure['classes'] and brace_depth < structure['classes'][-1]['depth']:
                structure['classes'][-1]['end'] = i
                if current_class_depth >= brace_depth:
                    current_class = None
        
        self._find_member_ends(lines, structure)
        return structure
    
    def _find_member_ends(self, lines: List[str], structure: Dict):
        """Find end lines for methods and properties."""
        all_members = structure['methods'] + structure['properties']
        all_members.sort(key=lambda x: x['start'])
        
        for i, member in enumerate(all_members):
            start = member['start']
            brace_count = 0
            in_body = False
            
            for j in range(start, len(lines)):
                stripped = lines[j].strip()
                brace_count += stripped.count('{') - stripped.count('}')
                
                if '{' in stripped:
                    in_body = True
                
                if in_body and brace_count == 0:
                    member['end'] = j
                    break
            
            if member['end'] is None:
                if i + 1 < len(all_members):
                    member['end'] = all_members[i + 1]['start'] - 1
                else:
                    member['end'] = len(lines) - 1
    
    def _chunk_by_members(self, filepath: str, lines: List[str], structure: Dict) -> List[ChunkData]:
        """Create chunks at method/property boundaries."""
        chunks = []
        
        all_members = [('method', m) for m in structure['methods']]
        all_members += [('property', p) for p in structure['properties']]
        all_members.sort(key=lambda x: x[1]['start'])
        
        for member_type, member in all_members:
            start = member['start']
            end = member['end'] or len(lines) - 1
            
            context_parts = []
            if structure['namespace']:
                context_parts.append(f"namespace {structure['namespace']}")
            if member.get('class'):
                context_parts.append(f"class {member['class']}")
            context_parts.append(f"{member_type} {member['name']}")
            context_header = " > ".join(context_parts)
            
            member_lines = lines[start:end + 1]
            content = "\n".join(member_lines)
            
            if len(member_lines) > self.max_chunk_lines:
                sub_chunks = self._split_large_content(
                    filepath, member_lines, start, context_header, member_type, "cs", ARCH_INDICATORS
                )
                chunks.extend(sub_chunks)
            elif len(content) >= self.min_chunk_chars:
                chunks.append(self._create_chunk(filepath, content, start, end, context_header, member_type))
        
        return chunks
    
    def _chunk_by_lines(self, filepath: str, lines: List[str], structure: Dict) -> List[ChunkData]:
        """Fallback: chunk by lines for files without clear structure."""
        context_parts = []
        if structure['namespace']:
            context_parts.append(f"namespace {structure['namespace']}")
        if structure['classes']:
            context_parts.append(f"class {structure['classes'][0]['name']}")
        context_header = " > ".join(context_parts) if context_parts else filepath.split('/')[-1]
        
        return self._split_large_content(filepath, lines, 0, context_header, "block", "cs", ARCH_INDICATORS)
    
    def _create_header_chunk(self, filepath: str, lines: List[str], structure: Dict) -> Optional[ChunkData]:
        """Create a chunk for file header."""
        if not structure['classes']:
            return None
        
        first_class = structure['classes'][0]
        header_end = first_class['start']
        
        for i in range(first_class['start'], min(first_class['start'] + 10, len(lines))):
            if '{' in lines[i]:
                header_end = i + 1
                break
        
        content = "\n".join(lines[:header_end])
        if len(content) < self.min_chunk_chars:
            return None
        
        context_header = f"FILE: {filepath.split('/')[-1]}"
        if structure['namespace']:
            context_header += f" > namespace {structure['namespace']}"
        if structure['classes']:
            context_header += f" > class {structure['classes'][0]['name']} (declaration)"
        
        return self._create_chunk(filepath, content, 0, header_end - 1, context_header, "file_header")
    
    def _create_chunk(
        self,
        filepath: str,
        content: str,
        start_line: int,
        end_line: int,
        context_header: str,
        chunk_type: str,
    ) -> ChunkData:
        """Create a ChunkData object."""
        content = self._truncate_content(content)
        is_arch = any(ind in content for ind in ARCH_INDICATORS)
        
        return ChunkData(
            id=self._generate_chunk_id(filepath, start_line, end_line, content),
            content=content,
            filepath=filepath,
            context_header=context_header,
            chunk_type=chunk_type,
            start_line=start_line,
            end_line=end_line,
            is_architecture_node=is_arch,
            embedding_text=self._create_embedding_text(context_header, filepath, chunk_type, content),
            file_type="cs",
        )
