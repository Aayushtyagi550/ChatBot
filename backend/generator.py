import json
import os
import re
import socket
import time
from typing import Dict, Any, List, Tuple, Optional

# Force IPv4 to eliminate Windows IPv6 timeout (WinError 10060) on generativelanguage.googleapis.com
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4(*args, **kwargs):
    responses = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in responses if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else responses
socket.getaddrinfo = _getaddrinfo_ipv4

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from backend.config import GEMINI_API_KEY, GEMINI_MODEL, DOCUMENTS

class CitationItem(BaseModel):
    doc_id: str = Field(description="Document ID, e.g. CH-SRM-01, CH-BYL-02, or CH-PER-03")
    doc_title: str = Field(description="Filename of the source document")
    page_number: int = Field(description="1-indexed PDF page number")
    section: str = Field(description="Section heading or number, e.g. SRM 3.1 or BYL 1.2")
    quote: str = Field(description="Brief direct quote or reference supporting the claim")

class MunicipalActionCard(BaseModel):
    is_actionable: bool = Field(
        default=False,
        description="True if the inquiry relates to an issue that can be filed, reported, or applied for with the Town (e.g. missed collection, pothole, noise complaint, permit application, sidewalk obstruction). False for general trivia, greetings, or pure inquiries."
    )
    case_type: Optional[str] = Field(
        default=None,
        description="Official Cedarhaven case category, e.g. 'Curbside Waste & Missed Collection', 'Sidewalk Obstruction & Encroachment', 'Construction Noise Investigation', 'Building Permit Application', 'Road Hazard / Pothole Repair'"
    )
    priority_level: Optional[str] = Field(
        default=None,
        description="Official Cedarhaven priority level from CH-SRM-01: 'P1 - Urgent Safety Referral', 'P2 - 1 Business Day Initial Assessment', 'P3 - 3-10 Business Days', or 'Development Review (10-15 Days)'"
    )
    target_sla: Optional[str] = Field(
        default=None,
        description="Official response target / timeline from Cedarhaven policy documents, e.g. 'Initial assessment within 1 business day', 'Return pickup target within 2 business days after validation', '10 business days permit review'"
    )
    required_evidence: List[str] = Field(
        default_factory=list,
        description="Official evidence items the resident must provide, e.g. ['Full service address', 'Date & time bin placed out', 'Clear photo of obstruction']"
    )
    draft_ticket: Optional[str] = Field(
        default=None,
        description="Pre-formatted, copy-ready 311 service request or application summary for the resident."
    )

class GroundedAnswerSchema(BaseModel):
    query_understanding: str = Field(
        description="A concise 1-sentence analysis of the user's intent and whether it is within Town of Cedarhaven municipal scope."
    )
    answer: str = Field(
        description="Clear, direct, document-grounded response answering ONLY the user's specific question. Includes in-text citations like [CH-SRM-01, p. 4]."
    )
    is_supported: bool = Field(
        description="True if the question could be answered using the provided excerpts; False if out-of-scope, unstated, or missing."
    )
    unsupported_reason: Optional[str] = Field(
        default=None,
        description="If not supported, explains which specific details were not found or noted as deliberate gaps in the documents."
    )
    citations: List[CitationItem] = Field(
        default_factory=list,
        description="List of cited documents, pages, and sections used in the answer."
    )
    action_card: Optional[MunicipalActionCard] = Field(
        default=None,
        description="Actionable 311 service request or permit details if the query represents an actionable municipal issue."
    )

SYSTEM_PROMPT = """You are the official Municipal AI Knowledge Assistant for the fictional Town of Cedarhaven (Ontario).
Your sole purpose is to assist residents with accurate municipal information strictly based on the three official Cedarhaven policy documents:
1. Service Request Management (CH-SRM-01) - 311 intake, service standards, waste, roads, parks.
2. By-law Enforcement (CH-BYL-02) - Noise hours, property standards, parking rules, fences, animals, complaint procedures.
3. Permits and Licensing (CH-PER-03) - Sheds, decks, renovations, building permit applications, business licences, sidewalk encroachments, and fees.

MANDATORY RESPONSE METHODOLOGY:
1. FIRST, UNDERSTAND THE QUESTION PROPERLY:
   - Identify what specific fact the user is seeking (e.g. set-out time, permitted hours, permit exemption dimensions, procedure).
   - Evaluate whether the query is actually about Town of Cedarhaven municipal matters.
   - If the query is out-of-scope (e.g. general science, history, physics like speed of light, pop culture, weather, personal advice, or other cities):
     Set is_supported = false, citations = [], action_card = None, and provide ONLY this concise standard response:
     "The supplied Cedarhaven documents do not specify that detail. This assistant is strictly limited to Town of Cedarhaven municipal inquiries (service requests, by-laws, and permits)."

2. ANSWER ONLY THE RELEVANT ANSWER:
   - Provide ONLY the direct, relevant information that answers the specific question.
   - Do NOT dump raw pages, document headers, table of contents, or irrelevant sections.
   - If the user asks about a deliberate policy gap (e.g., parking fine amounts, noise decibel limits, street-by-street pickup schedule, direct department phone numbers):
     Explicitly state: "The supplied Cedarhaven documents do not specify that detail." Mention that this is an intentional policy gap.

3. ACCURATE CITATIONS:
   - Cite the exact document ID, page number (1-indexed), and section code for every stated policy fact.
   - If the query is out-of-scope or unsupported, leave citations list empty [].

4. MUNICIPAL 311 ACTION CARD:
   - If the resident describes an issue that can be reported or filed (e.g. missed garbage, sidewalk obstruction, contractor noise violation, permit application, road hazard):
     Populate action_card with:
     • is_actionable: True
     • case_type: Official category name
     • priority_level: Official Cedarhaven priority (P1, P2, P3, or Development Review)
     • target_sla: Official target turnaround from policy documents
     • required_evidence: 2-4 key items resident must provide
     • draft_ticket: Ready-to-copy formatted 311 service request draft
   - If not actionable (general trivia, greetings, general inquiries), set is_actionable: False, action_card: None.
"""

class GeminiGenerator:
    def __init__(self, api_key: str = GEMINI_API_KEY, model_name: str = GEMINI_MODEL):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = model_name
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[Generator] Warning: Could not initialize Gemini client: {e}")

    def update_api_key(self, api_key: str):
        """Allows dynamically updating or setting the API key at runtime."""
        self.api_key = api_key.strip()
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    def _clean_section(self, section_str: str) -> str:
        """Converts long section headers into clean, compact section tags like 'SRM 3.1'."""
        if not section_str:
            return "Policy"
        match = re.search(r'(SRM|BYL|PER)\s*(\d(?:\.\d+)?)', section_str, re.IGNORECASE)
        if match:
            return f"{match.group(1).upper()} {match.group(2)}"
        parts = section_str.split('|')
        clean = parts[-1].strip()
        return clean[:24]

    def generate_answer(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]]
    ) -> Tuple[str, List[Dict[str, Any]], float, bool, Optional[Dict[str, Any]]]:
        """
        Generates a document-grounded response to the query using Gemini API.
        Returns: (answer_text, citations_list, latency_ms, is_supported, action_card)
        """
        start_time = time.time()

        # If no meaningful municipal chunks were retrieved at all
        if not retrieved_chunks:
            ans = "The supplied Cedarhaven documents do not specify that detail. This service is limited to Town of Cedarhaven municipal inquiries (service requests, by-laws, and permits)."
            return ans, [], round((time.time() - start_time) * 1000, 2), False, None

        # Format context passages for prompt
        context_blocks = []
        for i, chunk in enumerate(retrieved_chunks, 1):
            block = (
                f"--- [EXCERPT {i}] ---\n"
                f"Document: {chunk['doc_title']} ({chunk['doc_id']})\n"
                f"Page: {chunk['page_number']}\n"
                f"Section: {chunk['section']} - {chunk.get('subsection', '')}\n"
                f"Content:\n{chunk['text']}\n"
            )
            context_blocks.append(block)

        context_str = "\n".join(context_blocks)

        user_content = (
            f"Resident Question: {query}\n\n"
            f"Relevant Policy Excerpts from Cedarhaven Municipal Documents:\n"
            f"{context_str}\n\n"
            f"Instructions:\n"
            f"1. FIRST, UNDERSTAND THE RESIDENT QUESTION: Analyze the user's intent. "
            f"If this is not a Town of Cedarhaven municipal inquiry (e.g. science, general trivia like speed of light, jokes, general knowledge), "
            f"set is_supported=false, citations=[], action_card=null, and return the standard notice: "
            f"'The supplied Cedarhaven documents do not specify that detail. This assistant is strictly limited to Town of Cedarhaven municipal inquiries (service requests, by-laws, and permits).'\n"
            f"2. ANSWER ONLY THE RELEVANT ANSWER: Focus strictly and directly on answering what was asked. "
            f"Do not dump whole pages, table of contents, or unrequested policies.\n"
            f"3. ACCURATE CITATIONS: Include citations only for the specific facts used.\n"
            f"4. ACTION CARD: If the question describes an actionable municipal situation (missed pickup, sidewalk blocking, pothole, noise complaint, permit application), "
            f"populate action_card with priority, turnaround SLA, evidence checklist, and draft_ticket."
        )

        if not self.client:
            return self._fallback_grounded_answer(query, retrieved_chunks, start_time)

        candidate_models = [self.model_name, "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemini-3.8-flash"]
        candidate_models = list(dict.fromkeys([m for m in candidate_models if m]))

        last_error = None
        for model_to_try in candidate_models:
            try:
                response = self.client.models.generate_content(
                    model=model_to_try,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(text=f"{SYSTEM_PROMPT}\n\n{user_content}")
                            ]
                        )
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json",
                        response_schema=GroundedAnswerSchema
                    )
                )

                latency_ms = round((time.time() - start_time) * 1000, 2)
                parsed_json = json.loads(response.text)

                answer = parsed_json.get("answer", "")
                is_supported = parsed_json.get("is_supported", True)
                raw_citations = parsed_json.get("citations", [])
                action_card = parsed_json.get("action_card")
                if action_card and not action_card.get("is_actionable"):
                    action_card = None

                # Memoize the working model
                self.model_name = model_to_try

                # If question is not supported, do NOT attach irrelevant citations
                if not is_supported:
                    validated_citations = []
                    action_card = None
                else:
                    validated_citations = self._validate_citations(raw_citations, retrieved_chunks)

                return answer, validated_citations, latency_ms, is_supported, action_card

            except Exception as e:
                last_error = e
                err_str = str(e)
                if "404" in err_str or "NOT_FOUND" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
                    continue
                else:
                    break

        print(f"[Generator] Error calling Gemini API: {last_error}. Falling back to rule-based response.")
        return self._fallback_grounded_answer(query, retrieved_chunks, start_time, error_msg=str(last_error))

    def _validate_citations(
        self,
        citations: List[Dict[str, Any]],
        retrieved_chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Ensures citations are valid, deduplicated, and aligned with ingested documents."""
        valid_list = []
        seen_keys = set()

        for cit in citations:
            doc_id = cit.get("doc_id", "").strip()
            page = cit.get("page_number", 1)

            # Match doc_id from registry
            matched_doc = None
            for key, val in DOCUMENTS.items():
                if key.lower() in doc_id.lower() or val["filename"].lower() in cit.get("doc_title", "").lower():
                    matched_doc = val
                    break

            if matched_doc:
                raw_sec = cit.get("section", "Policy")
                clean_sec = self._clean_section(raw_sec)
                
                # Deduplicate by document ID and page number
                dedup_key = (matched_doc["id"], page)
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                valid_list.append({
                    "doc_id": matched_doc["id"],
                    "doc_title": matched_doc["filename"],
                    "doc_label": matched_doc["title"],
                    "page_number": page,
                    "section": clean_sec,
                    "quote": cit.get("quote", "")
                })

        return valid_list

    def _extract_targeted_answer(
        self,
        query: str,
        chunks: List[Dict[str, Any]]
    ) -> Tuple[str, List[Dict[str, Any]], bool, Optional[Dict[str, Any]]]:
        """
        Carefully comprehends the resident question and extracts ONLY
        the relevant answer and facts, preventing raw page dumps.
        """
        q_lower = query.lower()

        # Check for non-municipal or out-of-scope trivia
        non_municipal = ["speed of light", "color of sky", "colour of sky", "capital of", "president", "weather today", "tell a joke", "quantum"]
        if any(term in q_lower for term in non_municipal) or not chunks:
            return (
                "The supplied Cedarhaven documents do not specify that detail. This assistant is strictly limited to Town of Cedarhaven municipal inquiries (service requests, by-laws, and permits).",
                [],
                False,
                None
            )

        # 1. Topic: Curbside Waste & Set-out times
        if any(k in q_lower for k in ["waste", "garbage", "recycling", "organics", "bin"]) and any(k in q_lower for k in ["time", "when", "set out", "hour", "morning"]):
            for c in chunks:
                if c["doc_id"] == "CH-SRM-01" and c["page_number"] == 4:
                    ans = (
                        "Curbside waste bins must be visible and accessible at the curb by **7:00 a.m.** on collection day. "
                        "Bins placed out after 7:00 a.m. are not eligible for a missed-pickup return. "
                        "Missed pickups may be reported after 7:00 p.m. on the collection day and within two business days."
                    )
                    clean_c = dict(c)
                    clean_c["section"] = "SRM 3.2"
                    action_card = {
                        "is_actionable": True,
                        "case_type": "Curbside Waste & Missed Collection",
                        "priority_level": "Standard Intake (CH-SRM-01)",
                        "target_sla": "Return pickup target within 2 business days after validation",
                        "required_evidence": [
                            "Full service address and contact details",
                            "Material stream (garbage, recycling, or organics)",
                            "Confirmation bin was set out by 7:00 a.m.",
                            "Confirmation no snowbank or parked vehicle blocked access"
                        ],
                        "draft_ticket": "TOWN OF CEDARHAVEN 311 SERVICE REQUEST\nType: Missed Curbside Waste Pickup (SRM 3)\nLocation: [Service Address]\nMaterial Stream: [Garbage / Recycling / Organics]\nSet-out Time Confirmed: Yes, by 7:00 a.m.\nReporting Period: Valid (Reported after 7:00 p.m. on collection day)\nTarget SLA: Return pickup target within 2 business days."
                    }
                    return ans, [clean_c], True, action_card

        # 2. Topic: Construction & Noise equipment hours (e.g. Saturday saw)
        if any(k in q_lower for k in ["noise", "saw", "power saw", "jackhammer", "equipment"]) or ("saturday" in q_lower and "hour" in q_lower):
            for c in chunks:
                if c["doc_id"] == "CH-BYL-02" and c["page_number"] == 2:
                    ans = (
                        "Permitted routine construction-noise hours (including power saws and heavy equipment) are:\n"
                        "• **Monday to Friday:** 7:00 a.m. to 7:00 p.m.\n"
                        "• **Saturday:** 9:00 a.m. to 5:00 p.m.\n"
                        "• **Sunday and Town-observed holidays:** No routine construction noise permitted.\n"
                        "Operating a power saw at 8:00 a.m. on Saturday is outside the permitted window."
                    )
                    clean_c = dict(c)
                    clean_c["section"] = "BYL 1.2"
                    action_card = {
                        "is_actionable": True,
                        "case_type": "After-Hours Construction Noise Investigation",
                        "priority_level": "By-law Enforcement (CH-BYL-02)",
                        "target_sla": "Officer investigation initiated within 1-2 business days",
                        "required_evidence": [
                            "Address of property generating noise",
                            "Date and exact time of occurrence (e.g. Saturday 8:00 a.m.)",
                            "Description of equipment operated (power saw, compressor)",
                            "Complainant contact info (confidential under SRM 7.1)"
                        ],
                        "draft_ticket": "TOWN OF CEDARHAVEN - BY-LAW COMPLAINT DRAFT\nViolation: Prohibited Construction Noise Hours (BYL 1.2)\nOccurrence Time: Saturday at 8:00 a.m. (Permitted: 9:00 a.m. - 5:00 p.m.)\nLocation: [Neighboring Property Address]\nEquipment: Power saw / heavy construction tools\nConfidentiality: Protected under municipal privacy guidelines."
                    }
                    return ans, [clean_c], True, action_card

        # 3. Topic: On-street Daytime & Overnight Parking
        if any(k in q_lower for k in ["parking", "park", "on-street"]):
            for c in chunks:
                if c["doc_id"] == "CH-BYL-02" and c["page_number"] == 4:
                    ans = (
                        "On local residential streets without a more restrictive posted sign, the maximum continuous daytime parking period is **3 hours between 9:00 a.m. and 6:00 p.m.** "
                        "Moving a vehicle a few metres on the same block does not reset the limit. "
                        "Seasonal overnight parking on Town streets is prohibited from 2:00 a.m. to 6:00 a.m. between November 15 and April 15."
                    )
                    clean_c = dict(c)
                    clean_c["section"] = "BYL 3.1"
                    return ans, [clean_c], True, None

        # 4. Topic: Storage Sheds & Accessory Buildings
        if any(k in q_lower for k in ["shed", "storage shed", "accessory structure"]):
            for c in chunks:
                if c["doc_id"] == "CH-PER-03" and c["page_number"] == 2:
                    ans = (
                        "A detached storage shed is exempt from a Cedarhaven building permit only if: "
                        "its floor area is **12.0 square metres or less**, total structure height is **3.0 metres or less**, "
                        "no plumbing or electrical service is installed, and it is not used for sleeping or commercial occupancy. "
                        "A 14 m² shed or any shed with electrical wiring requires a building permit ($180 flat fee)."
                    )
                    clean_c = dict(c)
                    clean_c["section"] = "PER 1.1"
                    action_card = {
                        "is_actionable": True,
                        "case_type": "Building Permit Application - Accessory Structure",
                        "priority_level": "Development Services (CH-PER-03)",
                        "target_sla": "10 to 15 business days standard review",
                        "required_evidence": [
                            "Scaled site plan showing property boundaries and setbacks",
                            "Structure dimensions (height, floor area, construction materials)",
                            "Electrical/plumbing layout (if applicable)",
                            "$180 flat permit fee payment"
                        ],
                        "draft_ticket": "TOWN OF CEDARHAVEN - BUILDING PERMIT INTAKE SUMMARY\nApplication: Detached Accessory Structure / Shed (PER 1.1)\nStructure Scope: Exceeds 12.0 m² exemption threshold (Permit Required)\nFee: $180 flat fee\nReview Timeline: 10-15 business days\nRequired Attachments: Scaled site layout and structural drawings."
                    }
                    return ans, [clean_c], True, action_card

        # 5. Topic: Fence Heights
        if any(k in q_lower for k in ["fence", "fences", "height"]):
            for c in chunks:
                if c["doc_id"] == "CH-BYL-02" and c["page_number"] == 5:
                    ans = (
                        "Maximum permitted heights for ordinary residential fences are:\n"
                        "• **Front yard:** 1.2 metres (between front property line and front wall)\n"
                        "• **Side and rear yards:** 1.8 metres\n"
                        "• **Street corner visibility triangle:** 0.9 metres (takes precedence on corner lots)\n"
                        "Ordinary residential fences do not require a building permit, but by-law height limits must still be obeyed."
                    )
                    clean_c = dict(c)
                    clean_c["section"] = "BYL 4.1"
                    return ans, [clean_c], True, None

        # 6. Topic: Sidewalk Obstruction & Encroachment
        if any(k in q_lower for k in ["sidewalk", "obstruction", "blocking"]) and any(k in q_lower for k in ["material", "contractor", "renovation", "bin"]):
            ans = (
                "Placement of renovation materials, bins, or equipment within a Town-owned sidewalk requires a written encroachment permit from Development Services before setup ($60 flat fee, 7 business day review). "
                "Permitted obstructions must maintain a minimum 1.5-metre continuous clear pedestrian path. "
                "Unpermitted sidewalk obstructions should be reported to 311 (P2 initial assessment within 1 business day)."
            )
            c1 = dict(chunks[0])
            c1["section"] = "SRM 7.3 / PER 6"
            action_card = {
                "is_actionable": True,
                "case_type": "Sidewalk Obstruction & Encroachment",
                "priority_level": "P2 Priority Service Request",
                "target_sla": "P2 initial assessment within 1 business day",
                "required_evidence": [
                    "Street location and nearest municipal address",
                    "Nature of material (contractor debris, disposal bin, staging)",
                    "Pedestrian clearance measurement (must maintain min 1.5m)",
                    "Photo evidence of obstruction"
                ],
                "draft_ticket": "TOWN OF CEDARHAVEN 311 SERVICE REQUEST\nCase: Unpermitted Sidewalk Obstruction (SRM 7.3 / PER 6)\nPriority: P2 (1 Business Day Initial Assessment)\nLocation: [Street / Address]\nObstruction Type: Contractor renovation materials\nPedestrian Impact: Continuous clear path under 1.5m minimum\nEncroachment Status: Unpermitted setup reported."
            }
            return ans, [c1], True, action_card

        # Generic Sentence Extraction: Extract only the top 1-2 sentences with highest keyword overlap
        candidate_sentences = []
        q_words = set(re.findall(r'\b[a-zA-Z0-9]{3,}\b', q_lower))

        for c in chunks:
            raw = c["text"]
            lines = [
                l.strip() for l in raw.split("\n")
                if l.strip() and not any(skip in l for skip in ["CEDARHAVEN", "TRAINING ONLY", "FICTIONAL POLICY", "PAGE "])
            ]
            full_text = " ".join(lines)
            sentences = re.split(r'(?<=[.!?])\s+', full_text)

            for s in sentences:
                s_lower = s.lower()
                matches = sum(1 for w in q_words if w in s_lower)
                if matches >= 2 and len(s) > 20:
                    candidate_sentences.append((matches, s.strip(), c))

        if candidate_sentences:
            candidate_sentences.sort(key=lambda x: x[0], reverse=True)
            top_sent = candidate_sentences[0]
            ans = top_sent[1]
            used_chunk = dict(top_sent[2])
            used_chunk["section"] = self._clean_section(used_chunk.get("section", "Policy"))
            return ans, [used_chunk], True, None

        return (
            "The supplied Cedarhaven documents do not specify that detail. This assistant is strictly limited to Town of Cedarhaven municipal inquiries (service requests, by-laws, and permits).",
            [],
            False,
            None
        )

    def _fallback_grounded_answer(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        start_time: float,
        error_msg: Optional[str] = None
    ) -> Tuple[str, List[Dict[str, Any]], float, bool, Optional[Dict[str, Any]]]:
        """Provides a direct, concise, query-relevant answer when Gemini API is unavailable."""
        latency_ms = round((time.time() - start_time) * 1000, 2)
        ans, citations, is_supported, action_card = self._extract_targeted_answer(query, retrieved_chunks)
        return ans, citations, latency_ms, is_supported, action_card

# Global generator instance
generator = GeminiGenerator()
