-- CloudDeploy Hub: complete Supabase schema.
-- Supabase → SQL Editor → New query → paste this whole file → Run. Safe to run more than once.
-- The backend also creates missing tables on startup; this file lets you create them up front.

begin;

CREATE TABLE IF NOT EXISTS provider_verifications (
	provider VARCHAR(40) NOT NULL, 
	deployment_id INTEGER NOT NULL, 
	public_url VARCHAR(500) NOT NULL, 
	verified_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (provider)
);

CREATE TABLE IF NOT EXISTS users (
	id SERIAL NOT NULL, 
	google_sub VARCHAR(64), 
	email VARCHAR(320) NOT NULL, 
	name VARCHAR(200), 
	avatar_url VARCHAR(500), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_login_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (google_sub), 
	UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS auth_sessions (
	token_hash VARCHAR(64) NOT NULL, 
	user_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (token_hash), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_id ON auth_sessions (user_id);

CREATE TABLE IF NOT EXISTS github_connections (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	entered_username VARCHAR(100), 
	verified_login VARCHAR(100), 
	github_user_id INTEGER, 
	avatar_url VARCHAR(500), 
	token_encrypted TEXT, 
	scopes VARCHAR(300), 
	auth_method VARCHAR(20), 
	connected_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS oauth_states (
	state VARCHAR(100) NOT NULL, 
	purpose VARCHAR(20) NOT NULL, 
	user_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (state), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS projects (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	source_type VARCHAR(20) NOT NULL, 
	github_owner VARCHAR(100), 
	github_repo VARCHAR(100), 
	repo_private BOOLEAN, 
	branch VARCHAR(200), 
	root_dir VARCHAR(300) NOT NULL, 
	workspace_path VARCHAR(500), 
	upload_report_json TEXT, 
	analysis_json TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_projects_user_id ON projects (user_id);

CREATE TABLE IF NOT EXISTS deployments (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	project_id INTEGER NOT NULL, 
	project_name VARCHAR(120) NOT NULL, 
	github_username VARCHAR(100), 
	repository VARCHAR(200), 
	branch VARCHAR(200), 
	source_type VARCHAR(20) NOT NULL, 
	provider VARCHAR(40) NOT NULL, 
	deployment_id VARCHAR(200), 
	provider_resource_id VARCHAR(200), 
	status VARCHAR(20) NOT NULL, 
	provider_status VARCHAR(60), 
	public_url VARCHAR(500), 
	health_status VARCHAR(20) NOT NULL, 
	health_detail TEXT, 
	config_json TEXT, 
	meta_json TEXT, 
	error_message TEXT, 
	suggested_fix TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_deployments_project_id ON deployments (project_id);
CREATE INDEX IF NOT EXISTS ix_deployments_user_id ON deployments (user_id);

CREATE TABLE IF NOT EXISTS project_sources (
	project_id INTEGER NOT NULL, 
	archive BYTEA NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (project_id), 
	FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS deployment_events (
	id SERIAL NOT NULL, 
	deployment_id INTEGER NOT NULL, 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	level VARCHAR(10) NOT NULL, 
	message TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(deployment_id) REFERENCES deployments (id) ON DELETE CASCADE
);

-- Lock every table away from Supabase's public REST API (anon / publishable key).
-- The backend connects as the postgres role, which bypasses RLS, so it keeps full access.
alter table public.provider_verifications enable row level security;
revoke all on table public.provider_verifications from anon, authenticated;
alter table public.users enable row level security;
revoke all on table public.users from anon, authenticated;
alter table public.auth_sessions enable row level security;
revoke all on table public.auth_sessions from anon, authenticated;
alter table public.github_connections enable row level security;
revoke all on table public.github_connections from anon, authenticated;
alter table public.oauth_states enable row level security;
revoke all on table public.oauth_states from anon, authenticated;
alter table public.projects enable row level security;
revoke all on table public.projects from anon, authenticated;
alter table public.deployments enable row level security;
revoke all on table public.deployments from anon, authenticated;
alter table public.project_sources enable row level security;
revoke all on table public.project_sources from anon, authenticated;
alter table public.deployment_events enable row level security;
revoke all on table public.deployment_events from anon, authenticated;

commit;

-- Check: should list 9 tables, all with rowsecurity = true
select tablename, rowsecurity from pg_tables where schemaname = 'public' order by tablename;
