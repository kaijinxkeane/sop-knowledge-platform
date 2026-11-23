// Generated from the backend's OpenAPI spec by `npm run gen:api`. Do not edit.

export interface paths {
    "/api/v1/admin/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Audit */
        get: operations["list_audit_api_v1_admin_audit_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/audit/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Verify Audit */
        get: operations["verify_audit_api_v1_admin_audit_verify_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/grants/{grant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Grant */
        delete: operations["delete_grant_api_v1_admin_grants__grant_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/options": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Options
         * @description Every space, even ones the admin can't read: grants are given for them.
         */
        get: operations["options_api_v1_admin_options_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/roles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Roles */
        get: operations["list_roles_api_v1_admin_roles_get"];
        put?: never;
        /** Create Role */
        post: operations["create_role_api_v1_admin_roles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/roles/{role_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Role */
        delete: operations["delete_role_api_v1_admin_roles__role_id__delete"];
        options?: never;
        head?: never;
        /** Update Role */
        patch: operations["update_role_api_v1_admin_roles__role_id__patch"];
        trace?: never;
    };
    "/api/v1/admin/roles/{role_id}/grants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Add Grant */
        post: operations["add_grant_api_v1_admin_roles__role_id__grants_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Users */
        get: operations["list_users_api_v1_admin_users_get"];
        put?: never;
        /** Create */
        post: operations["create_api_v1_admin_users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get One */
        get: operations["get_one_api_v1_admin_users__user_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update User */
        patch: operations["update_user_api_v1_admin_users__user_id__patch"];
        trace?: never;
    };
    "/api/v1/admin/users/{user_id}/invite": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reinvite
         * @description New set-password link (also used as a password reset). The old password stops working.
         */
        post: operations["reinvite_api_v1_admin_users__user_id__invite_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users/{user_id}/reset-totp": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reset Totp
         * @description For a lost phone: the user sets up two-factor again at next sign-in.
         */
        post: operations["reset_totp_api_v1_admin_users__user_id__reset_totp_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users/{user_id}/unlock": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Unlock */
        post: operations["unlock_api_v1_admin_users__user_id__unlock_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/invite/accept": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Invite Accept */
        post: operations["invite_accept_api_v1_auth_invite_accept_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Refresh */
        post: operations["refresh_api_v1_auth_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/totp/enroll": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Totp Enroll */
        post: operations["totp_enroll_api_v1_auth_totp_enroll_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/totp/enroll/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Totp Enroll Confirm */
        post: operations["totp_enroll_confirm_api_v1_auth_totp_enroll_confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/totp/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Totp Verify */
        post: operations["totp_verify_api_v1_auth_totp_verify_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/classifications/bulk-approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Bulk Approve
         * @description Approve a group as proposed. Each item is checked on its own; one
         *     refusal does not stop the others.
         */
        post: operations["bulk_approve_api_v1_classifications_bulk_approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/classifications/queue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Queue */
        get: operations["queue_api_v1_classifications_queue_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/classifications/{proposal_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve */
        post: operations["approve_api_v1_classifications__proposal_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/classifications/{proposal_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reject
         * @description The labels in force stay as they are (quarantined or restricted).
         */
        post: operations["reject_api_v1_classifications__proposal_id__reject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conflicts/{conflict_id}/dismiss": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Dismiss Conflict */
        post: operations["dismiss_conflict_api_v1_conflicts__conflict_id__dismiss_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Conversations */
        get: operations["list_conversations_api_v1_conversations_get"];
        put?: never;
        /** Create Conversation */
        post: operations["create_conversation_api_v1_conversations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Messages
         * @description Your history. Old answers are re-checked against what you can read
         *     today: a part that cited an SOP you've since lost access to (moved team,
         *     note made restricted, retracted) is hidden (red-team, 2026-11-22).
         */
        get: operations["list_messages_api_v1_conversations__conversation_id__messages_get"];
        put?: never;
        /** Post Message */
        post: operations["post_message_api_v1_conversations__conversation_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Documents */
        get: operations["list_documents_api_v1_documents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/stages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Stages
         * @description Delivery stages in order (config/vault.yaml), for the Library's stage columns.
         */
        get: operations["list_stages_api_v1_documents_stages_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Document */
        get: operations["get_document_api_v1_documents__document_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/backlinks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Backlinks
         * @description Notes that link to or embed this one ("used in"). A linking note the user
         *     can't read is left out entirely: no title, no count.
         */
        get: operations["get_backlinks_api_v1_documents__document_id__backlinks_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/file": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get File
         * @description The original file (deck, PDF, note), only to users who may read it.
         */
        get: operations["get_file_api_v1_documents__document_id__file_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/names": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Review Names
         * @description Mark detected names as safe (e.g. a public figure, a venue) or as clients.
         *     Client names stay restricted; safe names stop flagging this and other notes.
         */
        post: operations["review_names_api_v1_documents__document_id__names_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/parts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Parts
         * @description Slides (with speaker notes) or PDF pages, for viewers and citations.
         */
        get: operations["get_parts_api_v1_documents__document_id__parts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Versions
         * @description Versions this person may read: approved ones (all versions for the
         *     note's editors), each judged by the labels it had (app.governance.history).
         */
        get: operations["get_versions_api_v1_documents__document_id__versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/versions/{commit}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Version
         * @description One version's text, for reading and side-by-side diffs. Notes: the file
         *     itself. Decks, PDFs and documents: the text the indexer reads (each slide's
         *     text and speaker notes, each page's text), plus their slides or pages.
         */
        get: operations["get_version_api_v1_documents__document_id__versions__commit__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/versions/{commit}/file": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Version File
         * @description The original file of one version (an old deck to download, an old PDF to view).
         */
        get: operations["get_version_file_api_v1_documents__document_id__versions__commit__file_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/gap-topics/{topic_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Set Topic Status */
        patch: operations["set_topic_status_api_v1_gap_topics__topic_id__patch"];
        trace?: never;
    };
    "/api/v1/handovers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Handovers */
        get: operations["list_handovers_api_v1_handovers_get"];
        put?: never;
        /** Create Handover */
        post: operations["create_handover_api_v1_handovers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/handovers/{handover_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Handover */
        get: operations["get_handover_api_v1_handovers__handover_id__get"];
        /** Update Handover */
        put: operations["update_handover_api_v1_handovers__handover_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/handovers/{handover_id}/acknowledge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Acknowledge */
        post: operations["acknowledge_api_v1_handovers__handover_id__acknowledge_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/handovers/{handover_id}/check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Check Handover */
        post: operations["check_handover_api_v1_handovers__handover_id__check_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/handovers/{handover_id}/comments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Comments */
        get: operations["list_comments_api_v1_handovers__handover_id__comments_get"];
        put?: never;
        /** Add Comment */
        post: operations["add_comment_api_v1_handovers__handover_id__comments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/handovers/{handover_id}/send": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Send Handover */
        post: operations["send_handover_api_v1_handovers__handover_id__send_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health/live": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Live */
        get: operations["live_api_v1_health_live_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Me */
        get: operations["get_me_api_v1_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me/bookmarks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Bookmarks */
        get: operations["list_bookmarks_api_v1_me_bookmarks_get"];
        put?: never;
        /** Add Bookmark */
        post: operations["add_bookmark_api_v1_me_bookmarks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me/bookmarks/{bookmark_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove Bookmark */
        delete: operations["remove_bookmark_api_v1_me_bookmarks__bookmark_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me/gaps": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** My Gaps */
        get: operations["my_gaps_api_v1_me_gaps_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me/gaps/request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Request Sop
         * @description Ask the space's leads for an SOP. They are told a request came in (no
         *     name); the question shows up, anonymously, in that space's gap topics.
         */
        post: operations["request_sop_api_v1_me_gaps_request_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/messages/{message_id}/feedback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Feedback */
        post: operations["feedback_api_v1_messages__message_id__feedback_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Note */
        post: operations["create_note_api_v1_notes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notes/{note_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Note */
        put: operations["update_note_api_v1_notes__note_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notes/{note_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve Direct
         * @description A lead approves the latest version without a request (e.g. an Obsidian edit).
         *     `version` is the governed hash shown by the diff, so what was read is what's approved.
         */
        post: operations["approve_direct_api_v1_notes__note_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notes/{note_id}/attachments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload Attachment
         * @description Attach a deck/PDF/DOCX to a note. The file lands beside the note and gets the
         *     note's space, but never looser than `internal` (an embed doesn't make it public).
         */
        post: operations["upload_attachment_api_v1_notes__note_id__attachments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notes/{note_id}/diff": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Diff
         * @description Unified diff between two versions (default: last approved -> latest).
         */
        get: operations["diff_api_v1_notes__note_id__diff_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notes/{note_id}/retire": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Retire
         * @description Retire a note: it stays in the Library (marked retired) but is never cited.
         */
        post: operations["retire_api_v1_notes__note_id__retire_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notes/{note_id}/source": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Source */
        get: operations["get_source_api_v1_notes__note_id__source_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notes/{note_id}/submit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Submit */
        post: operations["submit_api_v1_notes__note_id__submit_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notice": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Notice */
        get: operations["get_notice_api_v1_notice_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notice/acknowledge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Acknowledge Notice */
        post: operations["acknowledge_notice_api_v1_notice_acknowledge_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Notifications */
        get: operations["list_notifications_api_v1_notifications_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/{notification_id}/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mark Read */
        post: operations["mark_read_api_v1_notifications__notification_id__read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/project-shares": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Share Requests */
        get: operations["share_requests_api_v1_project_shares_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/project-shares/{share_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve Share
         * @description The department lead decides what the project may read: the whole space or
         *     selected folders/SOPs, until the project's end date. Read-only.
         */
        post: operations["approve_share_api_v1_project_shares__share_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/project-shares/{share_id}/decline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decline Share */
        post: operations["decline_share_api_v1_project_shares__share_id__decline_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/project-shares/{share_id}/revoke": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Revoke Share
         * @description Stop sharing now (any time, by that department's lead).
         */
        post: operations["revoke_share_api_v1_project_shares__share_id__revoke_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Projects */
        get: operations["list_projects_api_v1_projects_get"];
        put?: never;
        /** Create Project */
        post: operations["create_project_api_v1_projects_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Project */
        get: operations["get_project_api_v1_projects__project_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Project */
        patch: operations["update_project_api_v1_projects__project_id__patch"];
        trace?: never;
    };
    "/api/v1/projects/{project_id}/close": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Close */
        post: operations["close_api_v1_projects__project_id__close_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/members": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Add Members */
        post: operations["add_members_api_v1_projects__project_id__members_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/members/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove Member */
        delete: operations["remove_member_api_v1_projects__project_id__members__user_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/renew": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Renew
         * @description New end date (at most 6 months from today). Department shares stay as
         *     approved until their old date; each lead is asked once to confirm.
         */
        post: operations["renew_api_v1_projects__project_id__renew_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/shares": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Request Share */
        post: operations["request_share_api_v1_projects__project_id__shares_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/quick-search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Quick Search
         * @description Ctrl+K: titles of documents, programmes, stages, bookmarks and your
         *     conversations that match `q`. Titles only, never content.
         */
        get: operations["quick_search_api_v1_quick_search_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reports/bus-factor": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Bus Factor */
        get: operations["bus_factor_api_v1_reports_bus_factor_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reports/classification-accuracy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Accuracy
         * @description Counts only (no content): how often reviewers accepted the AI's labels.
         */
        get: operations["accuracy_api_v1_reports_classification_accuracy_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reports/conflicts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Conflicts */
        get: operations["conflicts_api_v1_reports_conflicts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reports/coverage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Coverage */
        get: operations["coverage_api_v1_reports_coverage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reports/gaps": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Hr Gaps */
        get: operations["hr_gaps_api_v1_reports_gaps_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reports/governance": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Governance Report
         * @description For a space's leads (approve) and auditors (view_audit: every space).
         */
        get: operations["governance_report_api_v1_reports_governance_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/retractions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Retract
         * @description Purge from the index and history; returns counts only (never the value).
         */
        post: operations["retract_api_v1_retractions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reviews": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Reviews */
        get: operations["list_reviews_api_v1_reviews_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reviews/{review_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Review */
        get: operations["get_review_api_v1_reviews__review_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reviews/{review_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve Request */
        post: operations["approve_request_api_v1_reviews__review_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reviews/{review_id}/request-changes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Request Changes */
        post: operations["request_changes_api_v1_reviews__review_id__request_changes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reviews/{review_id}/withdraw": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Withdraw */
        post: operations["withdraw_api_v1_reviews__review_id__withdraw_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Search Endpoint */
        get: operations["search_endpoint_api_v1_search_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/search/{search_id}/outcome": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Search Outcome
         * @description Sent by the Library when the user leaves a results page. Opening several
         *     results and using none is a gap signal in the user's own "gaps from your
         *     searches". Counts only: which documents were opened is not stored.
         */
        post: operations["search_outcome_api_v1_search__search_id__outcome_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/spaces": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Spaces
         * @description Spaces the user can use. Spaces with no access are not listed at all.
         */
        get: operations["list_spaces_api_v1_spaces_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/spaces/{space}/gaps": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Space Gaps */
        get: operations["space_gaps_api_v1_spaces__space__gaps_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/spaces/{space}/stale": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Stale */
        get: operations["stale_api_v1_spaces__space__stale_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AccessGapOut */
        AccessGapOut: {
            /** Document Id */
            document_id: string;
            /** Title */
            title: string;
        };
        /** AccessOut */
        AccessOut: {
            /** Sensitivity */
            sensitivity: string;
            /** Space */
            space: string;
        };
        /** AccuracyOut */
        AccuracyOut: {
            /** Approved As Proposed */
            approved_as_proposed: number;
            /** Approved With Edits */
            approved_with_edits: number;
            /** Pending */
            pending: number;
            /** Rejected */
            rejected: number;
            /** Space */
            space: string;
        };
        /** AckIn */
        AckIn: {
            /** Version */
            version: string;
        };
        /** Action */
        Action: {
            /** Due */
            due?: string | null;
            /**
             * Owner
             * @default
             */
            owner: string;
            /** Text */
            text: string;
        };
        /** ApproveShareIn */
        ApproveShareIn: {
            /** Document Ids */
            document_ids?: string[];
            /** Folders */
            folders?: string[];
            /**
             * Max Sensitivity
             * @default internal
             */
            max_sensitivity: string;
            /** Scope */
            scope: string;
        };
        /** AuditOut */
        AuditOut: {
            /** Action */
            action: string;
            /** Actor Id */
            actor_id: string | null;
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /** Id */
            id: number;
            /** Target Id */
            target_id: string | null;
            /** Target Type */
            target_type: string | null;
            /**
             * Ts
             * Format: date-time
             */
            ts: string;
        };
        /** BacklinkOut */
        BacklinkOut: {
            /** Embed */
            embed: boolean;
            /** Id */
            id: string;
            /** Kind */
            kind: string;
            /** Title */
            title: string;
        };
        /** Body_upload_attachment_api_v1_notes__note_id__attachments_post */
        Body_upload_attachment_api_v1_notes__note_id__attachments_post: {
            /** File */
            file: string;
            /** Original Link */
            original_link?: string | null;
            /** Source Tool */
            source_tool?: string | null;
        };
        /** BookmarkIn */
        BookmarkIn: {
            /** Part */
            part?: number | null;
            /**
             * Target Id
             * Format: uuid
             */
            target_id: string;
            /**
             * Target Type
             * @enum {string}
             */
            target_type: "document" | "conversation";
        };
        /** BookmarkOut */
        BookmarkOut: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Doc Type */
            doc_type?: string | null;
            /** Id */
            id: string;
            /** Kind */
            kind?: string | null;
            /** Part */
            part: number | null;
            /** Target Id */
            target_id: string;
            /** Target Type */
            target_type: string;
            /** Title */
            title: string;
        };
        /** BulkIn */
        BulkIn: {
            /** Ids */
            ids: string[];
        };
        /** BulkResult */
        BulkResult: {
            /** Error */
            error?: string | null;
            /** Id */
            id: string;
            /** Ok */
            ok: boolean;
        };
        /** BusFactorOut */
        BusFactorOut: {
            /** Leaving */
            leaving: components["schemas"]["LeavingOut"][];
            /** Single Author */
            single_author: components["schemas"]["BusItem"][];
        };
        /** BusItem */
        BusItem: {
            /** Author Leaving On */
            author_leaving_on: string | null;
            /** Document Id */
            document_id: string;
            /** Only Author */
            only_author: string;
            /** Space */
            space: string | null;
            /** Title */
            title: string;
        };
        /** CellOut */
        CellOut: {
            /** Programme */
            programme: string;
            /** Published */
            published: number;
            /** Stage */
            stage: string;
            /** Stale */
            stale: number;
            /** Titles */
            titles: string[] | null;
        };
        /** ChainOut */
        ChainOut: {
            /** Events */
            events: number;
            /** First Bad Id */
            first_bad_id: number | null;
            /** Ok */
            ok: boolean;
        };
        /** CodeIn */
        CodeIn: {
            /** Code */
            code: string;
            /** Token */
            token: string;
        };
        /** CommentIn */
        CommentIn: {
            /** Body */
            body: string;
        };
        /** CommentOut */
        CommentOut: {
            /** Author */
            author: string;
            /** Body */
            body: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
        };
        /** ConflictOut */
        ConflictOut: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Document A */
            document_a: string;
            /** Document B */
            document_b: string;
            /** Explanation */
            explanation: string;
            /** Id */
            id: string;
            /** Title A */
            title_a: string;
            /** Title B */
            title_b: string;
        };
        /** ConversationIn */
        ConversationIn: {
            /**
             * Title
             * @default
             */
            title: string;
        };
        /** ConversationOut */
        ConversationOut: {
            /** Id */
            id: string;
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** DecisionIn */
        DecisionIn: {
            /**
             * Comment
             * @default
             */
            comment: string;
        };
        /** DiffOut */
        DiffOut: {
            /** Added */
            added: number;
            /** Diff */
            diff: string;
            /** Document Id */
            document_id: string;
            /** From Commit */
            from_commit: string | null;
            /** Removed */
            removed: number;
            /** To Commit */
            to_commit: string | null;
            /** Version */
            version: string | null;
        };
        /** DirectApproveIn */
        DirectApproveIn: {
            /**
             * Comment
             * @default
             */
            comment: string;
            /** Version */
            version: string;
        };
        /** DocumentOut */
        DocumentOut: {
            /** Access */
            access: components["schemas"]["AccessOut"][];
            /**
             * Approved
             * @default false
             */
            approved: boolean;
            /** Doc Type */
            doc_type: string;
            /** Id */
            id: string;
            /** Kind */
            kind: string;
            /** Owner */
            owner: string | null;
            /**
             * Pending Change
             * @default false
             */
            pending_change: boolean;
            /** Programme */
            programme: string | null;
            /** Review Due */
            review_due?: string | null;
            /** Stage */
            stage: string | null;
            /** Status */
            status: string;
            /** Title */
            title: string;
            /** Vault Path */
            vault_path: string;
        };
        /** EnrollOut */
        EnrollOut: {
            /** Otpauth Uri */
            otpauth_uri: string;
            /** Secret */
            secret: string;
        };
        /** FeedbackIn */
        FeedbackIn: {
            /**
             * Comment
             * @default
             */
            comment: string;
            /** Helpful */
            helpful: boolean;
            /** Reason */
            reason?: ("wrong" | "outdated" | "missing_steps" | "unclear" | "other") | null;
        };
        /** GovernanceItem */
        GovernanceItem: {
            /**
             * Detail
             * @default {}
             */
            detail: {
                [key: string]: unknown;
            };
            /** Document Id */
            document_id: string;
            /** Space */
            space: string | null;
            /** Title */
            title: string | null;
        };
        /** GovernanceOut */
        GovernanceOut: {
            /**
             * Access Changes
             * @default []
             */
            access_changes: {
                [key: string]: unknown;
            }[];
            /** Changes Awaiting Review */
            changes_awaiting_review: components["schemas"]["GovernanceItem"][];
            /** Never Approved */
            never_approved: components["schemas"]["GovernanceItem"][];
            /**
             * Possible Instructions
             * @default []
             */
            possible_instructions: components["schemas"]["GovernanceItem"][];
            /** Published Outside Platform */
            published_outside_platform: components["schemas"]["GovernanceItem"][];
            /** Review Overdue */
            review_overdue: components["schemas"]["GovernanceItem"][];
            /** Self Approved */
            self_approved: components["schemas"]["GovernanceItem"][];
            /** Spaces */
            spaces: string[];
            /** Unattributed Edits */
            unattributed_edits: components["schemas"]["GovernanceItem"][];
        };
        /** GrantIn */
        GrantIn: {
            /** Actions */
            actions: string[];
            /**
             * Max Sensitivity
             * @default public
             * @enum {string}
             */
            max_sensitivity: "public" | "internal" | "restricted";
            /** Space */
            space: string | null;
        };
        /** GrantOut */
        GrantOut: {
            /** Actions */
            actions: string[];
            /** Id */
            id: string;
            /**
             * Max Sensitivity
             * @default public
             * @enum {string}
             */
            max_sensitivity: "public" | "internal" | "restricted";
            /** Space */
            space: string | null;
        };
        /** GroupOut */
        GroupOut: {
            /** Folder */
            folder: string;
            /** Group Key */
            group_key: string;
            /** Items */
            items: components["schemas"]["ProposalOut"][];
            /** Proposed Sensitivity */
            proposed_sensitivity: string;
            /** Proposed Space */
            proposed_space: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HandoverDetail */
        HandoverDetail: {
            /** Author */
            author: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Document Id */
            document_id: string;
            fields: components["schemas"]["HandoverFields"];
            /** Id */
            id: string;
            /** Issues */
            issues: components["schemas"]["IssueOut"][];
            /** Markdown */
            markdown: string;
            /** Mine */
            mine: boolean;
            /** Receivers */
            receivers: components["schemas"]["ReceiverOut"][];
            /** Sent At */
            sent_at: string | null;
            /** Space */
            space: string;
            /** Status */
            status: string;
            /** Title */
            title: string;
        };
        /** HandoverFields */
        HandoverFields: {
            /** Actions */
            actions?: components["schemas"]["Action"][];
            /**
             * Client
             * @default
             */
            client: string;
            /**
             * Contacts
             * @default
             */
            contacts: string;
            /**
             * Done
             * @default
             */
            done: string;
            /**
             * Files
             * @default
             */
            files: string;
            /**
             * No Upcoming Sessions
             * @default false
             */
            no_upcoming_sessions: boolean;
            /**
             * Preferences
             * @default
             */
            preferences: string;
            /**
             * Programme
             * @default
             */
            programme: string;
            /**
             * Risks
             * @default
             */
            risks: string;
            /** Sessions */
            sessions?: components["schemas"]["Session"][];
            /**
             * Stage
             * @default
             */
            stage: string;
        };
        /** HandoverIn */
        HandoverIn: {
            fields: components["schemas"]["HandoverFields"];
            /** Receivers */
            receivers: string[];
            /** Space */
            space: string;
            /** Title */
            title: string;
        };
        /** HandoverOut */
        HandoverOut: {
            /** Author */
            author: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Document Id */
            document_id: string;
            /** Id */
            id: string;
            /** Issues */
            issues: components["schemas"]["IssueOut"][];
            /** Mine */
            mine: boolean;
            /** Receivers */
            receivers: components["schemas"]["ReceiverOut"][];
            /** Sent At */
            sent_at: string | null;
            /** Space */
            space: string;
            /** Status */
            status: string;
            /** Title */
            title: string;
        };
        /** HandoverUpdate */
        HandoverUpdate: {
            fields?: components["schemas"]["HandoverFields"] | null;
            /** Receivers */
            receivers?: string[] | null;
        };
        /** HitOut */
        HitOut: {
            /** Doc Type */
            doc_type: string;
            /** Document Id */
            document_id: string;
            /** Heading */
            heading: string | null;
            /** Kind */
            kind: string;
            /** Matched */
            matched: string[];
            /** Part */
            part: string | null;
            /** Part Number */
            part_number: number | null;
            /** Programme */
            programme: string | null;
            /** Score */
            score: number;
            /** Snippet */
            snippet: string;
            /** Stage */
            stage: string | null;
            /** Title */
            title: string;
            /** Vault Path */
            vault_path: string;
        };
        /** HrTopicOut */
        HrTopicOut: {
            /** After Addressed 30D */
            after_addressed_30d: number | null;
            /** Before Addressed 30D */
            before_addressed_30d: number | null;
            /** By Role */
            by_role: {
                [key: string]: number;
            };
            /** Id */
            id: string;
            /** Label */
            label: string;
            /** People */
            people: number;
            /** Programme */
            programme: string | null;
            /** Questions */
            questions: number;
            /** Space */
            space: string;
            /** Stage */
            stage: string | null;
            /** Status */
            status: string;
        };
        /** InviteAcceptIn */
        InviteAcceptIn: {
            /** Password */
            password: string;
            /** Token */
            token: string;
        };
        /** InviteOut */
        InviteOut: {
            /** Expires In Hours */
            expires_in_hours: number;
            /** Invite Token */
            invite_token: string;
            user: components["schemas"]["UserOut"];
        };
        /** IssueOut */
        IssueOut: {
            /** Message */
            message: string;
            /** Section */
            section: string;
            /** Source */
            source: string;
        };
        /** LabelsIn */
        LabelsIn: {
            /** Sensitivity */
            sensitivity: string;
            /** Shared With */
            shared_with?: components["schemas"]["SharedIn"][];
            /** Space */
            space: string;
        };
        /** LeavingOut */
        LeavingOut: {
            /**
             * Leaving On
             * Format: date
             */
            leaving_on: string;
            /** Name */
            name: string;
            /** Owner Of */
            owner_of: number;
            /** Sole Author Of */
            sole_author_of: number;
        };
        /** LoginIn */
        LoginIn: {
            /** Email */
            email: string;
            /** Password */
            password: string;
        };
        /** MeOut */
        MeOut: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /** Global Actions */
            global_actions: string[];
            /** Home Space */
            home_space: string | null;
            /** Id */
            id: string;
            notice: components["schemas"]["NoticeStatus"];
            /** Roles */
            roles: string[];
            /** Scopes */
            scopes: {
                [key: string]: string;
            };
            /** Space Actions */
            space_actions: {
                [key: string]: string[];
            };
        };
        /** MembersIn */
        MembersIn: {
            /** User Ids */
            user_ids: string[];
        };
        /** MessageIn */
        MessageIn: {
            /** Content */
            content: string;
        };
        /** MessageOut */
        MessageOut: {
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /** Role */
            role: string;
            /** Sections */
            sections: {
                [key: string]: unknown;
            }[];
        };
        /** NamesIn */
        NamesIn: {
            /** Client */
            client?: string[];
            /** Safe */
            safe?: string[];
        };
        /** NoteCreateIn */
        NoteCreateIn: {
            /**
             * Body
             * @default
             */
            body: string;
            /**
             * Doc Type
             * @default sop
             */
            doc_type: string;
            /** Folder */
            folder?: string | null;
            /** Programme */
            programme?: string | null;
            /**
             * Sensitivity
             * @default internal
             */
            sensitivity: string;
            /** Space */
            space: string;
            /** Stage */
            stage?: string | null;
            /** Title */
            title: string;
        };
        /** NoteUpdateIn */
        NoteUpdateIn: {
            /** Base Version */
            base_version: string;
            /** Content */
            content: string;
        };
        /** NoticeOut */
        NoticeOut: {
            /** Acknowledged */
            acknowledged: boolean;
            /** Markdown */
            markdown: string;
            /** Version */
            version: string;
        };
        /** NoticeStatus */
        NoticeStatus: {
            /** Acknowledged */
            acknowledged: boolean;
            /** Version */
            version: string;
        };
        /** NotificationOut */
        NotificationOut: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Document Id */
            document_id: string | null;
            /** Id */
            id: string;
            /** Kind */
            kind: string;
            /** Read */
            read: boolean;
            /** Ref Id */
            ref_id: string | null;
            /** Title */
            title: string | null;
        };
        /**
         * OptionsOut
         * @description What the admin screens can offer when editing grants (labels only, no content).
         */
        OptionsOut: {
            /** Global Actions */
            global_actions: string[];
            /** Sensitivities */
            sensitivities: ("public" | "internal" | "restricted")[];
            /** Space Actions */
            space_actions: string[];
            /** Spaces */
            spaces: components["schemas"]["SpaceOption"][];
        };
        /** OutcomeIn */
        OutcomeIn: {
            /** Opened */
            opened: number;
            /** Used */
            used: boolean;
        };
        /** PartOut */
        PartOut: {
            /** Number */
            number: number;
            /** Part */
            part: string;
            /** Speaker Notes */
            speaker_notes: string;
            /** Title */
            title: string;
        };
        /** PersonOut */
        PersonOut: {
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
        /** PersonalGapOut */
        PersonalGapOut: {
            /** Count */
            count: number;
            /** Experts */
            experts: string[];
            /** Key */
            key: string;
            /** Label */
            label: string;
            /**
             * Last At
             * Format: date-time
             */
            last_at: string;
            /** Message */
            message: string;
            /** Programme */
            programme: string | null;
            /** Related */
            related: components["schemas"]["RelatedOut"][];
            /** Space */
            space: string | null;
            /** Stage */
            stage: string | null;
        };
        /** ProjectIn */
        ProjectIn: {
            /**
             * Ends On
             * Format: date
             */
            ends_on: string;
            /** Lead Id */
            lead_id?: string | null;
            /** Members */
            members?: string[];
            /** Name */
            name: string;
            /** Shares */
            shares?: components["schemas"]["ShareRequestIn"][];
        };
        /** ProjectOut */
        ProjectOut: {
            /** Active */
            active: boolean;
            /** Days Left */
            days_left: number;
            /**
             * Ends On
             * Format: date
             */
            ends_on: string;
            /** Folder */
            folder: string;
            /** Id */
            id: string;
            lead: components["schemas"]["PersonOut"];
            /** Members */
            members: components["schemas"]["PersonOut"][];
            /** My Role */
            my_role: string;
            /** Name */
            name: string;
            /** Shares */
            shares: components["schemas"]["ShareOut"][];
            /** Space */
            space: string;
            /**
             * Starts On
             * Format: date
             */
            starts_on: string;
        };
        /** ProjectUpdateIn */
        ProjectUpdateIn: {
            /** Lead Id */
            lead_id?: string | null;
            /** Name */
            name?: string | null;
        };
        /** ProposalOut */
        ProposalOut: {
            /** Confidence */
            confidence: number;
            current: components["schemas"]["LabelsIn"] | null;
            /** Decision */
            decision: string;
            /** Document Id */
            document_id: string;
            /** Evidence */
            evidence: string[];
            /** Id */
            id: string;
            /** Names */
            names: string[];
            /** Needs */
            needs: string;
            proposed: components["schemas"]["LabelsIn"] | null;
            /** Rationale */
            rationale: string;
            /** Safeguards */
            safeguards: string[];
            /** Stale */
            stale: boolean;
            /** Title */
            title: string;
            /** Vault Path */
            vault_path: string;
        };
        /** QuickConversation */
        QuickConversation: {
            /** Id */
            id: string;
            /** Title */
            title: string;
        };
        /** QuickDoc */
        QuickDoc: {
            /** Doc Type */
            doc_type: string;
            /** Id */
            id: string;
            /** Kind */
            kind: string;
            /** Programme */
            programme: string | null;
            /** Stage */
            stage: string | null;
            /** Title */
            title: string;
        };
        /** QuickOut */
        QuickOut: {
            /** Bookmarks */
            bookmarks: components["schemas"]["BookmarkOut"][];
            /** Conversations */
            conversations: components["schemas"]["QuickConversation"][];
            /** Documents */
            documents: components["schemas"]["QuickDoc"][];
            /** Programmes */
            programmes: string[];
            /** Stages */
            stages: string[];
        };
        /** ReceiverOut */
        ReceiverOut: {
            /** Acknowledged At */
            acknowledged_at: string | null;
            /** Name */
            name: string;
            /** User Id */
            user_id: string;
        };
        /** RelatedOut */
        RelatedOut: {
            /** Document Id */
            document_id: string;
            /** Space */
            space: string | null;
            /** Title */
            title: string;
        };
        /** RenewIn */
        RenewIn: {
            /**
             * Ends On
             * Format: date
             */
            ends_on: string;
        };
        /** RequestIn */
        RequestIn: {
            /** Key */
            key: string;
            /** Space */
            space: string;
        };
        /** RetractIn */
        RetractIn: {
            /** Document Id */
            document_id?: string | null;
            /** Value */
            value?: string | null;
        };
        /** ReviewOut */
        ReviewOut: {
            /** Comment */
            comment: string;
            /** Decided At */
            decided_at: string | null;
            /** Decided By */
            decided_by: string | null;
            /** Document Id */
            document_id: string;
            /**
             * Flags
             * @default []
             */
            flags: string[];
            /** Id */
            id: string;
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /** Requested By */
            requested_by: string;
            /** Self Review */
            self_review: boolean;
            /** Space */
            space: string | null;
            /** Stale */
            stale: boolean;
            /** Status */
            status: string;
            /** Summary */
            summary: string | null;
            /** Summary Pending */
            summary_pending: boolean;
            /** Title */
            title: string;
            /** Vault Path */
            vault_path: string;
        };
        /** RoleCreateIn */
        RoleCreateIn: {
            /**
             * Description
             * @default
             */
            description: string;
            /** Grants */
            grants?: components["schemas"]["GrantIn"][];
            /** Name */
            name: string;
        };
        /** RoleOut */
        RoleOut: {
            /** Description */
            description: string;
            /** Grants */
            grants: components["schemas"]["GrantOut"][];
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** User Count */
            user_count: number;
        };
        /** RoleUpdateIn */
        RoleUpdateIn: {
            /** Description */
            description: string;
        };
        /** SavedOut */
        SavedOut: {
            /** Commit */
            commit: string;
            /** Id */
            id: string;
            /** Vault Path */
            vault_path: string;
            /** Version */
            version: string;
        };
        /** SearchOut */
        SearchOut: {
            /** Results */
            results: components["schemas"]["HitOut"][];
            /** Search Id */
            search_id?: string | null;
            /** Semantic */
            semantic: boolean;
        };
        /** Session */
        Session: {
            /** What */
            what: string;
            /** When */
            when?: string | null;
        };
        /** SessionOut */
        SessionOut: {
            /** Access Token */
            access_token: string;
            /** Expires In */
            expires_in: number;
            /**
             * Token Type
             * @default bearer
             * @constant
             */
            token_type: "bearer";
        };
        /** ShareOut */
        ShareOut: {
            /** Approved Until */
            approved_until: string | null;
            /** Documents */
            documents: number;
            /** Folders */
            folders: string[];
            /** Id */
            id: string;
            /** In Force */
            in_force: boolean;
            /** Max Sensitivity */
            max_sensitivity: string;
            /** Note */
            note: string;
            /** Renewal Requested */
            renewal_requested: boolean;
            /** Scope */
            scope: string | null;
            /** Space */
            space: string;
            /** Status */
            status: string;
        };
        /** ShareRequestIn */
        ShareRequestIn: {
            /**
             * Note
             * @default
             */
            note: string;
            /** Space */
            space: string;
        };
        /** ShareRequestOut */
        ShareRequestOut: {
            /**
             * Ends On
             * Format: date
             */
            ends_on: string;
            /** Id */
            id: string;
            /** Members */
            members: number;
            /** Note */
            note: string;
            /** Project */
            project: string;
            /** Project Id */
            project_id: string;
            /** Project Lead */
            project_lead: string;
            /** Renewal Requested */
            renewal_requested: boolean;
            /** Space */
            space: string;
            /** Status */
            status: string;
        };
        /** SharedIn */
        SharedIn: {
            /** Sensitivity */
            sensitivity: string;
            /** Space */
            space: string;
        };
        /** SourceOut */
        SourceOut: {
            /** Content */
            content: string;
            /** Id */
            id: string;
            /** Vault Path */
            vault_path: string;
            /** Version */
            version: string;
        };
        /** SpaceOption */
        SpaceOption: {
            /** Name */
            name: string;
            /** Title */
            title: string;
        };
        /** SpaceOut */
        SpaceOut: {
            /** Access */
            access: string | null;
            /** Actions */
            actions: string[];
            /** Name */
            name: string;
            /** Title */
            title: string;
        };
        /** StaleOut */
        StaleOut: {
            /** Approved On */
            approved_on: string | null;
            /** Document Id */
            document_id: string;
            /** Overdue */
            overdue: boolean;
            /**
             * Review Due
             * Format: date
             */
            review_due: string;
            /** Title */
            title: string;
        };
        /** StepOut */
        StepOut: {
            /**
             * Expires In
             * @default 600
             */
            expires_in: number;
            /**
             * Status
             * @enum {string}
             */
            status: "totp_required" | "totp_enrollment_required";
            /** Token */
            token: string;
        };
        /** TokenIn */
        TokenIn: {
            /** Token */
            token: string;
        };
        /** TopicOut */
        TopicOut: {
            access_gap: components["schemas"]["AccessGapOut"] | null;
            /** Addressed At */
            addressed_at: string | null;
            /** Examples */
            examples: string[];
            /** Id */
            id: string;
            /** Label */
            label: string;
            /** Last 30 Days */
            last_30_days: number;
            /** People */
            people: number;
            /** Programme */
            programme: string | null;
            /** Questions */
            questions: number;
            /** Reasons */
            reasons: {
                [key: string]: number;
            };
            /** Space */
            space: string;
            /** Stage */
            stage: string | null;
            /** Status */
            status: string;
        };
        /** TopicStatusIn */
        TopicStatusIn: {
            /** Status */
            status: string;
        };
        /** UserCreateIn */
        UserCreateIn: {
            /** Display Name */
            display_name: string;
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Home Space */
            home_space?: string | null;
            /** Roles */
            roles?: string[];
        };
        /** UserOut */
        UserOut: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /** Home Space */
            home_space: string | null;
            /** Id */
            id: string;
            /** Invite Pending */
            invite_pending: boolean;
            /** Is Active */
            is_active: boolean;
            /** Last Login At */
            last_login_at: string | null;
            /** Leaving On */
            leaving_on?: string | null;
            /** Locked */
            locked: boolean;
            /** Roles */
            roles: string[];
            /** Totp Enabled */
            totp_enabled: boolean;
        };
        /** UserUpdateIn */
        UserUpdateIn: {
            /** Display Name */
            display_name?: string | null;
            /** Home Space */
            home_space?: string | null;
            /** Is Active */
            is_active?: boolean | null;
            /** Leaving On */
            leaving_on?: string | null;
            /** Roles */
            roles?: string[] | null;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** VersionContentOut */
        VersionContentOut: {
            /** Approved */
            approved: boolean;
            /** Author Name */
            author_name: string;
            /** Commit */
            commit: string;
            /**
             * Committed At
             * Format: date-time
             */
            committed_at: string;
            /** Content */
            content: string;
            /**
             * Parts
             * @default []
             */
            parts: components["schemas"]["PartOut"][];
        };
        /** VersionOut */
        VersionOut: {
            /**
             * Approved
             * @default false
             */
            approved: boolean;
            /** Author Name */
            author_name: string;
            /** Author Source */
            author_source: string;
            /** Authored By */
            authored_by: string | null;
            /** Commit */
            commit: string;
            /**
             * Committed At
             * Format: date-time
             */
            committed_at: string;
            /**
             * Latest
             * @default false
             */
            latest: boolean;
            /**
             * Live
             * @default false
             */
            live: boolean;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_audit_api_v1_admin_audit_get: {
        parameters: {
            query?: {
                action?: string | null;
                actor_id?: string | null;
                target_id?: string | null;
                since?: string | null;
                until?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    verify_audit_api_v1_admin_audit_verify_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChainOut"];
                };
            };
        };
    };
    delete_grant_api_v1_admin_grants__grant_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                grant_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    options_api_v1_admin_options_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OptionsOut"];
                };
            };
        };
    };
    list_roles_api_v1_admin_roles_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleOut"][];
                };
            };
        };
    };
    create_role_api_v1_admin_roles_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleCreateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_role_api_v1_admin_roles__role_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_role_api_v1_admin_roles__role_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleUpdateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_grant_api_v1_admin_roles__role_id__grants_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GrantIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_users_api_v1_admin_users_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"][];
                };
            };
        };
    };
    create_api_v1_admin_users_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserCreateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InviteOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_one_api_v1_admin_users__user_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_user_api_v1_admin_users__user_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserUpdateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reinvite_api_v1_admin_users__user_id__invite_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InviteOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reset_totp_api_v1_admin_users__user_id__reset_totp_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    unlock_api_v1_admin_users__user_id__unlock_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    invite_accept_api_v1_auth_invite_accept_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InviteAcceptIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StepOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                sop_refresh?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    refresh_api_v1_auth_refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                sop_refresh?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    totp_enroll_api_v1_auth_totp_enroll_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TokenIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EnrollOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    totp_enroll_confirm_api_v1_auth_totp_enroll_confirm_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CodeIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    totp_verify_api_v1_auth_totp_verify_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CodeIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    bulk_approve_api_v1_classifications_bulk_approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BulkIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BulkResult"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    queue_api_v1_classifications_queue_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GroupOut"][];
                };
            };
        };
    };
    approve_api_v1_classifications__proposal_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                proposal_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["LabelsIn"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reject_api_v1_classifications__proposal_id__reject_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                proposal_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    dismiss_conflict_api_v1_conflicts__conflict_id__dismiss_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conflict_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_conversations_api_v1_conversations_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_conversation_api_v1_conversations_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConversationIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_messages_api_v1_conversations__conversation_id__messages_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_message_api_v1_conversations__conversation_id__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_documents_api_v1_documents_get: {
        parameters: {
            query?: {
                space?: string | null;
                programme?: string | null;
                stage?: string | null;
                doc_type?: string | null;
                kind?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_stages_api_v1_documents_stages_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": string[];
                };
            };
        };
    };
    get_document_api_v1_documents__document_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_backlinks_api_v1_documents__document_id__backlinks_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacklinkOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_file_api_v1_documents__document_id__file_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    review_names_api_v1_documents__document_id__names_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NamesIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_parts_api_v1_documents__document_id__parts_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PartOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_versions_api_v1_documents__document_id__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_version_api_v1_documents__document_id__versions__commit__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
                commit: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionContentOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_version_file_api_v1_documents__document_id__versions__commit__file_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
                commit: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    set_topic_status_api_v1_gap_topics__topic_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                topic_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TopicStatusIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_handovers_api_v1_handovers_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HandoverOut"][];
                };
            };
        };
    };
    create_handover_api_v1_handovers_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HandoverIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HandoverOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_handover_api_v1_handovers__handover_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                handover_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HandoverDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_handover_api_v1_handovers__handover_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                handover_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HandoverUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HandoverOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    acknowledge_api_v1_handovers__handover_id__acknowledge_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                handover_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HandoverOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    check_handover_api_v1_handovers__handover_id__check_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                handover_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IssueOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_comments_api_v1_handovers__handover_id__comments_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                handover_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommentOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_comment_api_v1_handovers__handover_id__comments_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                handover_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CommentIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommentOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_handover_api_v1_handovers__handover_id__send_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                handover_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HandoverOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_api_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    live_api_v1_health_live_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    get_me_api_v1_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeOut"];
                };
            };
        };
    };
    list_bookmarks_api_v1_me_bookmarks_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookmarkOut"][];
                };
            };
        };
    };
    add_bookmark_api_v1_me_bookmarks_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BookmarkIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookmarkOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    remove_bookmark_api_v1_me_bookmarks__bookmark_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bookmark_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    my_gaps_api_v1_me_gaps_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonalGapOut"][];
                };
            };
        };
    };
    request_sop_api_v1_me_gaps_request_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RequestIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    feedback_api_v1_messages__message_id__feedback_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                message_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FeedbackIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_note_api_v1_notes_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NoteCreateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_note_api_v1_notes__note_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                note_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NoteUpdateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    approve_direct_api_v1_notes__note_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                note_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DirectApproveIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_attachment_api_v1_notes__note_id__attachments_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                note_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_attachment_api_v1_notes__note_id__attachments_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    diff_api_v1_notes__note_id__diff_get: {
        parameters: {
            query?: {
                from?: string | null;
                to?: string | null;
            };
            header?: never;
            path: {
                note_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DiffOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    retire_api_v1_notes__note_id__retire_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                note_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_source_api_v1_notes__note_id__source_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                note_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_api_v1_notes__note_id__submit_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                note_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_notice_api_v1_notice_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoticeOut"];
                };
            };
        };
    };
    acknowledge_notice_api_v1_notice_acknowledge_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AckIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_notifications_api_v1_notifications_get: {
        parameters: {
            query?: {
                unread?: boolean;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NotificationOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    mark_read_api_v1_notifications__notification_id__read_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                notification_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    share_requests_api_v1_project_shares_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ShareRequestOut"][];
                };
            };
        };
    };
    approve_share_api_v1_project_shares__share_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                share_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApproveShareIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ShareRequestOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    decline_share_api_v1_project_shares__share_id__decline_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                share_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revoke_share_api_v1_project_shares__share_id__revoke_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                share_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_projects_api_v1_projects_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"][];
                };
            };
        };
    };
    create_project_api_v1_projects_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_api_v1_projects__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_project_api_v1_projects__project_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectUpdateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    close_api_v1_projects__project_id__close_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_members_api_v1_projects__project_id__members_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MembersIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    remove_member_api_v1_projects__project_id__members__user_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    renew_api_v1_projects__project_id__renew_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RenewIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    request_share_api_v1_projects__project_id__shares_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ShareRequestIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    quick_search_api_v1_quick_search_get: {
        parameters: {
            query: {
                q: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuickOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    bus_factor_api_v1_reports_bus_factor_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusFactorOut"];
                };
            };
        };
    };
    accuracy_api_v1_reports_classification_accuracy_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AccuracyOut"][];
                };
            };
        };
    };
    conflicts_api_v1_reports_conflicts_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConflictOut"][];
                };
            };
        };
    };
    coverage_api_v1_reports_coverage_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CellOut"][];
                };
            };
        };
    };
    hr_gaps_api_v1_reports_gaps_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HrTopicOut"][];
                };
            };
        };
    };
    governance_report_api_v1_reports_governance_get: {
        parameters: {
            query?: {
                space?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GovernanceOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    retract_api_v1_retractions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RetractIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_reviews_api_v1_reviews_get: {
        parameters: {
            query?: {
                state?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_review_api_v1_reviews__review_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                review_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    approve_request_api_v1_reviews__review_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                review_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DecisionIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    request_changes_api_v1_reviews__review_id__request_changes_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                review_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DecisionIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    withdraw_api_v1_reviews__review_id__withdraw_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                review_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    search_endpoint_api_v1_search_get: {
        parameters: {
            query: {
                q: string;
                space?: string | null;
                programme?: string | null;
                stage?: string | null;
                doc_type?: string | null;
                kind?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    search_outcome_api_v1_search__search_id__outcome_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                search_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OutcomeIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_spaces_api_v1_spaces_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SpaceOut"][];
                };
            };
        };
    };
    space_gaps_api_v1_spaces__space__gaps_get: {
        parameters: {
            query?: {
                status?: string | null;
            };
            header?: never;
            path: {
                space: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TopicOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stale_api_v1_spaces__space__stale_get: {
        parameters: {
            query?: {
                within_days?: number;
            };
            header?: never;
            path: {
                space: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StaleOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
