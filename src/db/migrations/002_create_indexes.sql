CREATE INDEX IF NOT EXISTS idx_videos_creator_id__video_created_at
    ON videos(creator_id, video_created_at);

CREATE INDEX IF NOT EXISTS idx_video_snapshots_created_at
    ON video_snapshots(created_at);

CREATE INDEX IF NOT EXISTS idx_video_snapshots_video_id__created_at
    ON video_snapshots(video_id, created_at);

