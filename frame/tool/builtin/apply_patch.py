import os
import re
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from frame.tool.base import (
    BaseTool,
    Property,
    ToolDesc,
    ToolParameters,
    ToolResponse,
    ValidationResult,
)


class ApplyPatchTool(BaseTool):
    """基于 unified diff (unified format) 的最小化 patch 应用工具。

    """

    def __init__(self, workspace_root: str, max_patch_size: int = 1_000_000):
        super().__init__(name="apply_patch", description="基于 unified diff 应用最小化补丁，原子操作")
        self.workspace_root = os.path.realpath(workspace_root)
        self.max_patch_size = int(max_patch_size)

    @classmethod
    def desc(cls) -> ToolDesc:
        params = ToolParameters(
            properties={
                "patch": Property(type="string", description="unified diff 文本")
            },
            required=["patch"],
        )
        return ToolDesc(name="apply_patch", description="Apply unified diff patch", parameters=params)

    def valid_paras(self, params: Dict[str, Any]) -> ValidationResult:
        patch = params.get("patch")
        if not isinstance(patch, str) or not patch.strip():
            return ValidationResult(valid=False, message="patch must be a non-empty string")

        if len(patch) > self.max_patch_size:
            return ValidationResult(valid=False, message="patch too large")

        # extract target paths and validate they are within workspace
        targets: List[str] = []
        for m in re.finditer(r'^\+\+\+\s+(\S+)', patch, flags=re.MULTILINE):
            raw = m.group(1).split('\t', 1)[0]
            if raw == "/dev/null":
                continue
            rel = self._strip_ab_prefix(raw)
            # disallow absolute paths and path traversal
            if os.path.isabs(rel):
                return ValidationResult(valid=False, message=f"absolute paths not allowed: {rel}")
            norm = os.path.normpath(rel)
            if norm.startswith(".."):
                return ValidationResult(valid=False, message=f"path traversal not allowed: {rel}")
            abs_path = os.path.realpath(os.path.join(self.workspace_root, norm))
            if not abs_path.startswith(self.workspace_root):
                return ValidationResult(valid=False, message=f"path outside workspace: {rel}")
            targets.append(norm)

        return ValidationResult(valid=True, parsed_params={"patch": patch, "targets": list(dict.fromkeys(targets))})

    def _strip_ab_prefix(self, p: str) -> str:
        # strip common git prefixes a/ b/
        if p.startswith("a/") or p.startswith("b/"):
            return p[2:]
        return p

    def _parse_unified_diff(self, patch: str) -> List[Dict[str, Any]]:
        """Parse a minimal subset of unified diff into per-file hunks.

        Returns a list of dicts with keys: old_path, new_path, hunks (list).
        Each hunk is dict(old_start, old_count, new_start, new_count, lines).
        """
        lines = patch.splitlines()
        i = 0
        files: List[Dict[str, Any]] = []
        while i < len(lines):
            line = lines[i]
            if line.startswith("--- "):
                old_path = line[4:].split('\t', 1)[0].strip()
                i += 1
                if i >= len(lines) or not lines[i].startswith("+++ "):
                    raise Exception("invalid diff: missing +++ after ---")
                new_path = lines[i][4:].split('\t', 1)[0].strip()
                i += 1

                hunks: List[Dict[str, Any]] = []
                while i < len(lines) and not lines[i].startswith("--- "):
                    if lines[i].startswith("@@ "):
                        hdr = lines[i]
                        m = re.match(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@", hdr)
                        if not m:
                            raise Exception("invalid hunk header")
                        old_start = int(m.group(1))
                        old_count = int(m.group(2)) if m.group(2) else 1
                        new_start = int(m.group(3))
                        new_count = int(m.group(4)) if m.group(4) else 1
                        i += 1
                        hunk_lines: List[str] = []
                        while i < len(lines) and not lines[i].startswith("@@ ") and not lines[i].startswith("--- "):
                            # skip git marker for no-newline
                            if lines[i].startswith("\\ No newline"):
                                i += 1
                                continue
                            hunk_lines.append(lines[i])
                            i += 1
                        hunks.append(
                            {
                                "old_start": old_start,
                                "old_count": old_count,
                                "new_start": new_start,
                                "new_count": new_count,
                                "lines": hunk_lines,
                            }
                        )
                    else:
                        # skip headers/metadata lines until next hunk or file
                        i += 1

                files.append({"old_path": old_path, "new_path": new_path, "hunks": hunks})
            else:
                i += 1

        return files

    def _apply_hunks(self, original_lines: List[str], hunks: List[Dict[str, Any]]) -> List[str]:
        pos = 0
        result: List[str] = []
        for h in hunks:
            old_start_index = max(0, h["old_start"] - 1)
            if old_start_index > len(original_lines):
                raise Exception("hunk starts beyond end of file")

            # append unchanged section
            result.extend(original_lines[pos:old_start_index])
            idx = old_start_index

            for hl in h["lines"]:
                if hl == "":
                    prefix = ""
                    content = ""
                else:
                    prefix = hl[0]
                    content = hl[1:] if len(hl) > 1 else ""

                if prefix == " ":
                    if idx >= len(original_lines) or original_lines[idx] != content:
                        raise Exception("context mismatch when applying hunk")
                    result.append(original_lines[idx])
                    idx += 1
                elif prefix == "-":
                    if idx >= len(original_lines) or original_lines[idx] != content:
                        raise Exception("deletion mismatch when applying hunk")
                    idx += 1
                elif prefix == "+":
                    result.append(content)
                else:
                    # ignore unexpected lines
                    pass

            pos = idx

        result.extend(original_lines[pos:])
        return result

    def _read_text_file(self, path: str) -> List[str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                txt = f.read()
        except UnicodeDecodeError:
            raise Exception("binary file or non-utf8 encoding not supported")
        return txt.splitlines()

    def _write_atomic(self, target: str, content: str) -> None:
        dirpath = os.path.dirname(target)
        os.makedirs(dirpath, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".copilot_patch_", dir=dirpath)
        os.close(fd)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, target)

    def _apply_all(self, files: List[Dict[str, Any]]) -> List[str]:
        # Prepare new contents for all files first (no writes yet)
        new_contents: Dict[str, str] = {}
        for item in files:
            old_raw = item["old_path"]
            new_raw = item["new_path"]
            old_rel = None if old_raw == "/dev/null" else self._strip_ab_prefix(old_raw)
            new_rel = None if new_raw == "/dev/null" else self._strip_ab_prefix(new_raw)

            # choose target relative path (new_rel if present else old_rel)
            target_rel = new_rel or old_rel
            if not target_rel:
                raise Exception("unable to determine target path for patch file")

            abs_target = os.path.realpath(os.path.join(self.workspace_root, target_rel))
            if not abs_target.startswith(self.workspace_root):
                raise Exception(f"path outside workspace: {target_rel}")

            if os.path.exists(abs_target):
                original_lines = self._read_text_file(abs_target)
            else:
                original_lines = []

            updated_lines = self._apply_hunks(original_lines, item["hunks"])
            # join with newline and ensure final newline
            content = "\n".join(updated_lines)
            if content and not content.endswith("\n"):
                content = content + "\n"
            new_contents[abs_target] = content

        # All patches validated/constructed; write atomically
        applied_files: List[str] = []
        tmp_paths: List[Tuple[str, str]] = []
        try:
            # write to temp files first
            for abs_target, content in new_contents.items():
                dirpath = os.path.dirname(abs_target)
                os.makedirs(dirpath, exist_ok=True)
                fd, tmp = tempfile.mkstemp(prefix=".copilot_patch_", dir=dirpath)
                os.close(fd)
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(content)
                tmp_paths.append((tmp, abs_target))

            # replace originals
            for tmp, abs_target in tmp_paths:
                os.replace(tmp, abs_target)
                applied_files.append(os.path.relpath(abs_target, self.workspace_root))

            return applied_files
        except Exception:
            # cleanup any temp files
            for tmp, _ in tmp_paths:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
            raise

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        patch = params.get("patch")
        if not isinstance(patch, str):
            return ToolResponse(tool_name=self.name, status="error", output="invalid patch parameter")
        try:
            files = self._parse_unified_diff(patch)
        except Exception as e:
            return ToolResponse(tool_name=self.name, status="error", output=str(e))

        try:
            applied = self._apply_all(files)
            return ToolResponse(
                tool_name=self.name,
                status="success",
                output=f"applied {len(applied)} files",
                details={"applied_files": applied},
            )
        except Exception as e:
            return ToolResponse(tool_name=self.name, status="error", output=str(e))


if __name__ == "__main__":
    print("ApplyPatchTool module")
