"""
Workflow Generator Routes
API endpoints for natural language workflow generation
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..workflow_generator import get_workflow_generator

router = APIRouter(prefix="/workflow-gen", tags=["workflow-generator"])


class GenerateRequest(BaseModel):
    """Request to generate a workflow"""
    prompt: str
    model: str = "llama3.2"


class ApprovalRequest(BaseModel):
    """Request to approve/reject a workflow"""
    action: str  # "approve" or "reject"
    reason: Optional[str] = None


class DeployRequest(BaseModel):
    """Request to deploy a workflow"""
    n8n_url: str = "http://localhost:5678"
    api_key: Optional[str] = None


@router.post("/generate")
async def generate_workflow(request: GenerateRequest):
    """
    Generate a workflow from natural language description

    The workflow will be created in 'pending_review' status and must be
    approved before deployment.
    """
    generator = get_workflow_generator()

    try:
        workflow = await generator.generate_from_prompt(
            prompt=request.prompt,
            model=request.model
        )

        return {
            "status": "generated",
            "workflow_id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "preview": workflow.to_n8n_json(),
            "message": "Workflow generated. Please review and approve before deployment."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.get("/pending")
def list_pending_workflows():
    """List all workflows pending review"""
    generator = get_workflow_generator()
    return generator.get_pending_workflows()


@router.get("/{workflow_id}")
def get_workflow(workflow_id: str):
    """Get a specific workflow by ID"""
    generator = get_workflow_generator()
    workflow = generator.get_workflow(workflow_id)

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return workflow


@router.post("/{workflow_id}/review")
def review_workflow(workflow_id: str, request: ApprovalRequest):
    """Approve or reject a workflow"""
    generator = get_workflow_generator()

    if request.action == "approve":
        success = generator.approve_workflow(workflow_id)
        if success:
            return {"status": "approved", "workflow_id": workflow_id}
    elif request.action == "reject":
        success = generator.reject_workflow(workflow_id, request.reason or "")
        if success:
            return {"status": "rejected", "workflow_id": workflow_id}
    else:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

    raise HTTPException(status_code=404, detail="Workflow not found")


@router.post("/{workflow_id}/deploy")
async def deploy_workflow(workflow_id: str, request: DeployRequest):
    """
    Deploy an approved workflow to n8n

    The workflow must be in 'approved' status before deployment.
    """
    generator = get_workflow_generator()

    # Check workflow exists and is approved
    workflow = generator.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if workflow["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Workflow must be approved before deployment. Current status: {workflow['status']}"
        )

    n8n_id = await generator.deploy_workflow(
        workflow_id,
        n8n_url=request.n8n_url,
        api_key=request.api_key
    )

    if n8n_id:
        return {
            "status": "deployed",
            "workflow_id": workflow_id,
            "n8n_workflow_id": n8n_id
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to deploy to n8n")


@router.get("/")
def get_workflow_gen_stats():
    """Get workflow generation statistics"""
    generator = get_workflow_generator()
    return generator.get_stats()


@router.get("/templates/list")
def list_templates():
    """List available workflow templates"""
    generator = get_workflow_generator()
    return {
        "templates": [
            {
                "id": name,
                "description": template["description"],
                "triggers": [t.value for t in template["triggers"]],
                "actions": [a.value for a in template["actions"]]
            }
            for name, template in generator._templates.items()
        ]
    }
