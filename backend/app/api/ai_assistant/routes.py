from pathlib import Path
from flask import request, current_app
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.utils import secure_filename
import uuid

from app.services import ai_assistant_service, ai_text_service, object_storage_service, submission_service
from app.services.upload_validation import UploadValidationError, validate_upload_filename
from app.models.ai import AiConversation
from app.extensions import db
from app.utils.auth import internal_user_required
from app.utils.response import error_response, success_response, validation_error
from app.utils.fiscal_year import FiscalYearError, validate_fiscal_year

from . import ai_bp


@ai_bp.route('/tool-calls/<int:tool_call_id>/downloads/<int:file_index>', methods=['GET'])
@jwt_required()
@internal_user_required
def download_tool_file(tool_call_id, file_index):
    from app.services import ai_report_tools, ai_tool_registry
    try:
        return ai_report_tools.download_tool_file(tool_call_id, file_index, get_jwt_identity())
    except ai_tool_registry.AiToolError as exc:
        return error_response(exc.message, status_code=exc.status_code)

@ai_bp.route('/conversations/<int:conversation_id>/upload', methods=['POST'])
@jwt_required()
@internal_user_required
def upload_attachment(conversation_id):
    user_id = int(get_jwt_identity())
    convo = db.session.get(AiConversation, conversation_id)
    if not convo or convo.user_id != user_id:
        return error_response('Conversation not found.', status_code=404)
        
    upload = request.files.get('file')
    if not upload or not getattr(upload, 'filename', '').strip():
        return validation_error({'file': 'A file is required for attachment.'})
        
    try:
        original_filename = validate_upload_filename(upload.filename)
        mime_type = submission_service._validate_upload_constraints(original_filename, upload)
    except (UploadValidationError, submission_service.SubmissionError) as e:
        return error_response(e.message, status_code=422)
        
    extension = Path(original_filename).suffix
    stored_filename = f'{uuid.uuid4().hex}{extension}'
    
    # Store directly since it's just a temporary attachment before full submission
    destination_path = submission_service._submission_root() / 'attachments' / stored_filename
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    with object_storage_service.storage_transaction() as storage_tx:
        upload.seek(0)
        upload.save(destination_path)
        storage_tx.track_local_path(destination_path)

        stored_object = object_storage_service.store_file(
            destination_path,
            source_module='ai_chat_uploads',
            original_filename=original_filename,
            content_type=mime_type,
            uploaded_by=user_id,
            metadata={'conversation_id': conversation_id},
            tracker=storage_tx,
        )

        # Clean up local file after object storage write
        try:
            destination_path.unlink()
        except OSError:
            pass

        db.session.commit()
        storage_tx.commit()
        
    return success_response(data={
        'attachment_stored_object_id': stored_object.id,
        'attachment_filename': original_filename
    })

@ai_bp.route('/rewrite-text', methods=['POST'])
@jwt_required()
@internal_user_required
def rewrite_text():
    data = request.get_json(silent=True) or {}
    text = data.get('text')
    if not isinstance(text, str) or not text.strip():
        return validation_error({'text': 'Text is required'})

    try:
        result = ai_text_service.rewrite_text(
            text=text,
            mode=data.get('mode') or 'polish',
            context_label=data.get('context_label'),
            user_id=get_jwt_identity(),
        )
        return success_response(data=result, message='AI rewrite generated successfully')
    except ai_text_service.AiTextRewriteError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@ai_bp.route('/conversations', methods=['POST'])
@jwt_required()
@internal_user_required
def create_conversation():
    data = request.get_json(silent=True) or {}
    try:
        conversation = ai_assistant_service.create_conversation(
            user_id=get_jwt_identity(),
            title=data.get('title'),
        )
        return success_response(data=conversation, message='AI conversation created', status_code=201)
    except ai_assistant_service.AiAssistantError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@ai_bp.route('/conversations', methods=['GET'])
@jwt_required()
@internal_user_required
def list_conversations():
    try:
        include_archived = str(request.args.get('include_archived', '')).lower() in {'1', 'true', 'yes'}
        return success_response(data=ai_assistant_service.list_conversations(
            get_jwt_identity(),
            include_archived=include_archived,
        ))
    except ai_assistant_service.AiAssistantError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@ai_bp.route('/tools', methods=['GET'])
@jwt_required()
@internal_user_required
def list_available_tools():
    try:
        catalog = ai_assistant_service.list_available_tools(get_jwt_identity())
        return success_response(data=catalog, meta={
            'capabilities': ai_assistant_service.get_capability_summary(get_jwt_identity(), catalog=catalog),
        })
    except ai_assistant_service.AiAssistantError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@ai_bp.route('/conversations/<int:conversation_id>', methods=['GET'])
@jwt_required()
@internal_user_required
def get_conversation(conversation_id):
    try:
        return success_response(data=ai_assistant_service.get_conversation(conversation_id, get_jwt_identity()))
    except ai_assistant_service.AiAssistantError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@ai_bp.route('/conversations/<int:conversation_id>', methods=['PATCH'])
@jwt_required()
@internal_user_required
def update_conversation(conversation_id):
    data = request.get_json(silent=True) or {}
    try:
        conversation = ai_assistant_service.update_conversation(
            conversation_id=conversation_id,
            user_id=get_jwt_identity(),
            title=data.get('title') if 'title' in data else None,
            status=data.get('status') if 'status' in data else None,
        )
        return success_response(data=conversation, message='AI conversation updated')
    except ai_assistant_service.AiAssistantError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@ai_bp.route('/conversations/<int:conversation_id>/messages', methods=['POST'])
@jwt_required()
@internal_user_required
def send_message(conversation_id):
    data = request.get_json(silent=True) or {}
    message = data.get('message')
    if not isinstance(message, str) or not message.strip():
        return validation_error({'message': 'Message is required'})

    try:
        fiscal_year = data.get('fiscal_year')
        if fiscal_year not in (None, ''):
            fiscal_year = validate_fiscal_year(int(fiscal_year))
        else:
            fiscal_year = None
        result = ai_assistant_service.send_message(
            conversation_id=conversation_id,
            content=message,
            user_id=get_jwt_identity(),
            fiscal_year=fiscal_year,
            attachment_stored_object_id=data.get('attachment_stored_object_id')
        )
        return success_response(data=result, message='AI message processed')
    except (FiscalYearError, ValueError) as exc:
        return validation_error({'fiscal_year': str(exc)})
    except ai_assistant_service.AiAssistantError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@ai_bp.route('/tool-calls/<int:tool_call_id>/confirm', methods=['POST'])
@jwt_required()
@internal_user_required
def confirm_tool_call(tool_call_id):
    try:
        result = ai_assistant_service.confirm_tool_call(tool_call_id, get_jwt_identity())
        return success_response(data=result, message='AI action confirmed and executed')
    except ai_assistant_service.AiAssistantError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@ai_bp.route('/tool-calls/<int:tool_call_id>/cancel', methods=['POST'])
@jwt_required()
@internal_user_required
def cancel_tool_call(tool_call_id):
    try:
        result = ai_assistant_service.cancel_tool_call(tool_call_id, get_jwt_identity())
        return success_response(data=result, message='AI action cancelled')
    except ai_assistant_service.AiAssistantError as exc:
        return error_response(exc.message, status_code=exc.status_code)
