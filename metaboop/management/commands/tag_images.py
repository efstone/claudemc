"""
Management command to tag images with AI-generated keywords.

Usage:
    python manage.py tag_images /path/to/images
    python manage.py tag_images /path/to/image.jpg --minecraft
    python manage.py tag_images /path/to/folder --recursive --force
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from metaboop.processor import SUPPORTED_EXTENSIONS, process_folder, process_image


class Command(BaseCommand):
    help = 'Process images with Claude Vision API and write keyword metadata'

    def add_arguments(self, parser):
        parser.add_argument('path', type=str, help='Path to image file or directory')
        parser.add_argument(
            '--minecraft',
            action='store_true',
            help='Use Minecraft-specific analysis mode',
        )
        parser.add_argument(
            '--no-recursive',
            action='store_true',
            help='Do not recurse into subdirectories',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Reprocess images even if already processed',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Analyze images but do not write metadata',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=0.5,
            help='Seconds between API calls (default: 0.5)',
        )

    def handle(self, *args, **options):
        path = Path(options['path'])
        is_minecraft = options['minecraft']
        recursive = not options['no_recursive']
        force = options['force']
        dry_run = options['dry_run']
        delay = options['delay']

        mode = "Minecraft" if is_minecraft else "Standard"
        self.stdout.write(f"Mode: {mode}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN - no metadata will be written")
            )

        def progress_callback(result):
            if result.was_skipped:
                self.stdout.write(
                    self.style.NOTICE(f"  SKIP (already processed): {result.file_path}")
                )
            elif result.success:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  OK: {result.file_path} ({len(result.keywords)} keywords)"
                    )
                )
                if dry_run and result.keywords:
                    self.stdout.write(f"      Keywords: {', '.join(result.keywords)}")
            else:
                self.stdout.write(
                    self.style.ERROR(f"  FAIL: {result.file_path} - {result.error}")
                )

        if path.is_file():
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                self.stderr.write(
                    self.style.ERROR(f"Unsupported file format: {path.suffix}")
                )
                return

            self.stdout.write(f"Processing single file: {path}")
            result = process_image(str(path), is_minecraft, force, dry_run)
            progress_callback(result)

        elif path.is_dir():
            self.stdout.write(f"Processing directory: {path}")
            self.stdout.write(f"  Recursive: {recursive}")

            results = process_folder(
                str(path),
                is_minecraft=is_minecraft,
                recursive=recursive,
                force=force,
                dry_run=dry_run,
                delay=delay,
                callback=progress_callback,
            )

            # Summary
            total = len(results)
            success = sum(1 for r in results if r.success and not r.was_skipped)
            skipped = sum(1 for r in results if r.was_skipped)
            failed = sum(1 for r in results if not r.success)

            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Complete: {success} processed, {skipped} skipped, "
                    f"{failed} failed (of {total} total)"
                )
            )

        else:
            self.stderr.write(self.style.ERROR(f"Path not found: {path}"))
