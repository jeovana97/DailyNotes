"""
Suíte completa de testes do Gerenciador de Tarefas (menu Agendamentos).
Valida todos os 12 critérios obrigatórios de conclusão:
1. Cadastro de nova tarefa
2. Edição das informações
3. Alteração de status
4. Inclusão de várias atualizações no histórico
5. Preservação das informações anteriores
6. Conclusão e reabertura de tarefas
7. Identificação de tarefas atrasadas
8. Pesquisa, filtros, abas, ordenação e indicadores
9. Funcionamento dos lembretes e prevenção de duplicidade
10. Persistência após fechar e abrir o aplicativo
11. Compatibilidade com funcionalidades atuais do Diário + migração de agendamentos legados
12. Compatibilidade com backup e restauração do banco SQLite
"""

import datetime
import os
import tempfile
import unittest

import customtkinter as ctk

from database.connection import get_connection
from database.migrations import init_db
from services.authentication_service import AuthenticationService
from services.backup_service import BackupService
from services.diary_service import DiaryService
from services.schedule_service import ScheduleService
from services.task_service import TaskService
from utils.notification_utils import parse_toast_protocol_url
from views.main_window import MainWindow


class TestTaskManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "tasks_test.db")
        init_db(self.db_path)

        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.user, _ = self.auth_service.create_initial_admin(
            "tester_tasks", "Usuário Tarefas", "senha123"
        )
        self.task_service = TaskService(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # ------------------------------------------------------------------
    # Critérios 1, 2, 3, 4, 5 e 6: CRUD, Status, Histórico, Conclusão e Reabertura
    # ------------------------------------------------------------------
    def test_01_to_06_crud_history_preservation_complete_and_reopen(self):
        t0 = datetime.datetime(2026, 11, 26, 9, 0, 0)
        task, msg = self.task_service.create_task(
            user_id=self.user.id,
            title="Corrigir problema na emissão de notas fiscais",
            description="Erro na validação do XML do cliente.",
            start_date="2026-11-26",
            due_date="2026-11-30",
            due_time="17:00",
            priority="alta",
            status="pendente",
            category="Suporte",
            reminder_enabled=True,
            reminders=[
                {
                    "reminder_type": "due_day",
                    "remind_time": "09:00",
                    "is_active": True,
                }
            ],
            now=t0,
        )
        self.assertIsNotNone(task, msg)
        self.assertEqual(task.title, "Corrigir problema na emissão de notas fiscais")
        self.assertEqual(task.priority, "alta")
        self.assertEqual(task.status, "pendente")
        self.assertEqual(task.category, "Suporte")
        self.assertIsNone(task.completed_at)
        self.assertEqual(len(task.history), 1)
        self.assertEqual(task.history[0].note, "Tarefa cadastrada.")

        # 2. Edição de informações (não pode apagar nem sobrescrever o histórico)
        t1 = datetime.datetime(2026, 11, 26, 10, 0, 0)
        ok_upd, msg_upd = self.task_service.update_task(
            task_id=task.id,
            user_id=self.user.id,
            title="Corrigir emissão de NF-e (Urgente)",
            description="Erro na tag de ICMS no XML do cliente.",
            start_date="2026-11-26",
            due_date="2026-11-29",
            due_time="18:00",
            priority="urgente",
            status="pendente",
            category="Fiscal",
            reminder_enabled=True,
            reminders=[
                {
                    "reminder_type": "due_day",
                    "remind_time": "09:00",
                    "is_active": True,
                }
            ],
            now=t1,
        )
        self.assertTrue(ok_upd, msg_upd)
        edited = self.task_service.get_task_by_id(task.id, self.user.id)
        self.assertEqual(edited.title, "Corrigir emissão de NF-e (Urgente)")
        self.assertEqual(edited.priority, "urgente")
        self.assertEqual(edited.category, "Fiscal")
        self.assertEqual(len(edited.history), 1)  # Histórico inicial preservado

        # 3 & 4. Alteração de status + várias atualizações cronológicas no histórico
        t2 = datetime.datetime(2026, 11, 26, 11, 15, 0)
        entry2, _ = self.task_service.add_progress_update(
            task.id, self.user.id, "Iniciada análise do problema.", new_status="em_andamento", now=t2
        )
        self.assertIsNotNone(entry2)
        self.assertEqual(entry2.status_at_time, "em_andamento")

        t3 = datetime.datetime(2026, 11, 27, 14, 0, 0)
        self.task_service.add_progress_update(
            task.id, self.user.id, "Solicitado XML ao cliente.", now=t3
        )

        t4 = datetime.datetime(2026, 11, 28, 16, 30, 0)
        self.task_service.add_progress_update(
            task.id, self.user.id, "Identificada a causa do problema na alíquota.", now=t4
        )

        t5 = datetime.datetime(2026, 11, 29, 10, 0, 0)
        self.task_service.add_progress_update(
            task.id, self.user.id, "Correção realizada e aguardando validação.", now=t5
        )

        # 5 & 6. Conclusão automática com registro de data/hora + preservação do histórico
        t6 = datetime.datetime(2026, 11, 29, 15, 45, 0)
        ok_done, _ = self.task_service.complete_task(task.id, self.user.id, now=t6)
        self.assertTrue(ok_done)
        done_task = self.task_service.get_task_by_id(task.id, self.user.id)
        self.assertEqual(done_task.status, "concluida")
        self.assertEqual(done_task.completed_at, "2026-11-29 15:45:00")
        self.assertEqual(len(done_task.history), 6)

        # Lembretes devem ser desativados ao concluir
        self.assertTrue(all(not r.is_active for r in done_task.reminders))

        # Reabertura mantendo TODO o histórico anterior
        t7 = datetime.datetime(2026, 11, 30, 8, 30, 0)
        ok_reopen, _ = self.task_service.reopen_task(
            task.id, self.user.id, target_status="em_andamento", note="Cliente pediu ajuste extra no PDF.", now=t7
        )
        self.assertTrue(ok_reopen)
        reopened = self.task_service.get_task_by_id(task.id, self.user.id)
        self.assertEqual(reopened.status, "em_andamento")
        self.assertIsNone(reopened.completed_at)
        self.assertEqual(len(reopened.history), 7)

        # Verifica ordem cronológica e preservação exata de cada registro anterior
        notes_in_order = [h.note for h in reopened.history]
        self.assertEqual(
            notes_in_order,
            [
                "Tarefa cadastrada.",
                "Iniciada análise do problema.",
                "Solicitado XML ao cliente.",
                "Identificada a causa do problema na alíquota.",
                "Correção realizada e aguardando validação.",
                "Tarefa concluída.",
                "Cliente pediu ajuste extra no PDF.",
            ],
        )
        self.assertEqual(reopened.history[0].status_at_time, "pendente")
        self.assertEqual(reopened.history[1].status_at_time, "em_andamento")
        self.assertEqual(reopened.history[5].status_at_time, "concluida")
        self.assertEqual(reopened.history[6].status_at_time, "em_andamento")

    # ------------------------------------------------------------------
    # Critérios 7 e 8: Atrasadas, Pesquisa (título + histórico), Abas, Filtros, Ordenação e Indicadores
    # ------------------------------------------------------------------
    def test_07_and_08_overdue_search_filters_sorting_and_counts(self):
        now_ref = datetime.datetime(2026, 11, 26, 14, 0, 0)

        # Tarefa 1: Atrasada (ontem), Urgente, Pendente
        t_late, _ = self.task_service.create_task(
            self.user.id,
            title="Enviar relatório fiscal",
            description="Fechamento mensal",
            due_date="2026-11-25",
            due_time="18:00",
            priority="urgente",
            status="pendente",
            now=datetime.datetime(2026, 11, 20, 9, 0, 0),
        )
        self.task_service.add_progress_update(
            t_late.id, self.user.id, "Falta protocolo SEFAZ assinado.", now=datetime.datetime(2026, 11, 24, 15, 0, 0)
        )

        # Tarefa 2: Hoje (horário ainda futuro), Média, Em andamento
        t_today, _ = self.task_service.create_task(
            self.user.id,
            title="Reunião de alinhamento",
            description="Revisar metas",
            due_date="2026-11-26",
            due_time="16:30",
            priority="media",
            status="em_andamento",
            now=datetime.datetime(2026, 11, 22, 10, 0, 0),
        )

        # Tarefa 3: Hoje mas horário já passou -> também atrasada!
        t_today_late, _ = self.task_service.create_task(
            self.user.id,
            title="Ligar para fornecedor",
            due_date="2026-11-26",
            due_time="11:00",
            priority="alta",
            status="pendente",
            now=datetime.datetime(2026, 11, 23, 10, 0, 0),
        )

        # Tarefa 4: Próximos dias, Baixa, Pendente
        t_next, _ = self.task_service.create_task(
            self.user.id,
            title="Organizar documentação interna",
            due_date="2026-12-02",
            priority="baixa",
            status="pendente",
            now=datetime.datetime(2026, 11, 25, 10, 0, 0),
        )

        # Tarefa 5: Data passada mas CONCLUÍDA -> NÃO é atrasada
        t_done, _ = self.task_service.create_task(
            self.user.id,
            title="Backup semanal",
            due_date="2026-11-20",
            priority="media",
            status="concluida",
            now=datetime.datetime(2026, 11, 19, 10, 0, 0),
        )

        # Tarefa 6: Cancelada
        t_cancel, _ = self.task_service.create_task(
            self.user.id,
            title="Evento adiado",
            due_date="2026-11-28",
            priority="baixa",
            status="cancelada",
            now=datetime.datetime(2026, 11, 21, 10, 0, 0),
        )

        # Indicadores de produtividade
        counts = self.task_service.get_summary_counts(self.user.id, now=now_ref)
        self.assertEqual(counts["total"], 6)
        self.assertEqual(counts["pendentes"], 3)
        self.assertEqual(counts["em_andamento"], 1)
        self.assertEqual(counts["concluidas"], 1)
        self.assertEqual(counts["canceladas"], 1)
        self.assertEqual(counts["atrasadas"], 2)  # t_late + t_today_late
        self.assertEqual(counts["hoje"], 2)       # t_today + t_today_late
        self.assertEqual(counts["proximos_dias"], 1)  # t_next

        # Abas individuais
        atrasadas = self.task_service.list_tasks(self.user.id, tab="atrasadas", now=now_ref)
        self.assertEqual({t.id for t in atrasadas}, {t_late.id, t_today_late.id})

        hoje = self.task_service.list_tasks(self.user.id, tab="hoje", now=now_ref)
        self.assertEqual({t.id for t in hoje}, {t_today.id, t_today_late.id})

        proximos = self.task_service.list_tasks(self.user.id, tab="proximos_dias", now=now_ref)
        self.assertEqual([t.id for t in proximos], [t_next.id])

        canceladas = self.task_service.list_tasks(self.user.id, tab="canceladas", now=now_ref)
        self.assertEqual([t.id for t in canceladas], [t_cancel.id])

        # Pesquisa pelo conteúdo adicionado no HISTÓRICO (sem acento e case-insensitive)
        by_history = self.task_service.list_tasks(self.user.id, search_query="sefaz", now=now_ref)
        self.assertEqual([t.id for t in by_history], [t_late.id])

        # Pesquisa pelo título sem acento
        by_title = self.task_service.list_tasks(self.user.id, search_query="reuniao", now=now_ref)
        self.assertEqual([t.id for t in by_title], [t_today.id])

        # Filtros por período, status e prioridade
        by_period = self.task_service.list_tasks(
            self.user.id, date_from="2026-11-26", date_to="2026-11-30", now=now_ref
        )
        self.assertEqual({t.id for t in by_period}, {t_today.id, t_today_late.id, t_cancel.id})

        by_prio = self.task_service.list_tasks(self.user.id, priority_filter="urgente", now=now_ref)
        self.assertEqual([t.id for t in by_prio], [t_late.id])

        by_status = self.task_service.list_tasks(self.user.id, status_filter="concluida", now=now_ref)
        self.assertEqual([t.id for t in by_status], [t_done.id])

        # Ordenações: Prioridade, Data prevista, Data de cadastro e Última atualização
        sorted_prio = self.task_service.list_tasks(self.user.id, sort_by="priority", sort_desc=False, now=now_ref)
        self.assertEqual(sorted_prio[0].priority, "urgente")
        self.assertEqual(sorted_prio[1].priority, "alta")

        sorted_due = self.task_service.list_tasks(self.user.id, sort_by="due_date", sort_desc=False, now=now_ref)
        self.assertEqual(sorted_due[0].id, t_done.id)  # 2026-11-20

        sorted_created_desc = self.task_service.list_tasks(self.user.id, sort_by="created_at", sort_desc=True, now=now_ref)
        self.assertEqual(sorted_created_desc[0].id, t_next.id)  # criada em 2026-11-25

        sorted_updated_desc = self.task_service.list_tasks(self.user.id, sort_by="updated_at", sort_desc=True, now=now_ref)
        self.assertEqual(sorted_updated_desc[0].id, t_next.id)

    # ------------------------------------------------------------------
    # Critério 9: Lembretes (personalizado, vencimento, antecipado, atrasada, anti-duplicidade e snooze)
    # ------------------------------------------------------------------
    def test_09_reminders_types_dedup_snooze_and_protocol(self):
        dispatched_log = []

        def fake_notify(task, reminder, title, message):
            dispatched_log.append((task.id, reminder.reminder_type, title, message))

        # Tarefa A: Aviso antecipado (1 hora antes) + Aviso no dia do vencimento (14:00)
        task_a, _ = self.task_service.create_task(
            self.user.id,
            title="Apresentação para diretoria",
            due_date="2026-11-26",
            due_time="14:00",
            priority="alta",
            reminder_enabled=True,
            reminders=[
                {"reminder_type": "advance", "advance_minutes": 60, "remind_time": "14:00", "is_active": True},
                {"reminder_type": "due_day", "remind_time": "14:00", "is_active": True},
            ],
        )

        # 12:30 -> ainda não atingiu 13:00 (1h antes)
        res_early = self.task_service.reminder_service.check_and_notify_due_reminders(
            user_id=self.user.id,
            now=datetime.datetime(2026, 11, 26, 12, 30, 0),
            notify_callback=fake_notify,
        )
        self.assertEqual(len(res_early), 0)

        # 13:05 -> dispara aviso antecipado 1 única vez
        res_adv = self.task_service.reminder_service.check_and_notify_due_reminders(
            user_id=self.user.id,
            now=datetime.datetime(2026, 11, 26, 13, 5, 0),
            notify_callback=fake_notify,
        )
        self.assertEqual(len(res_adv), 1)
        self.assertEqual(res_adv[0]["reminder"].reminder_type, "advance")

        # 13:10 -> NÃO deve repetir o aviso antecipado
        res_adv_dup = self.task_service.reminder_service.check_and_notify_due_reminders(
            user_id=self.user.id,
            now=datetime.datetime(2026, 11, 26, 13, 10, 0),
            notify_callback=fake_notify,
        )
        self.assertEqual(len(res_adv_dup), 0)

        # 14:00 -> dispara aviso no dia do vencimento
        res_due = self.task_service.reminder_service.check_and_notify_due_reminders(
            user_id=self.user.id,
            now=datetime.datetime(2026, 11, 26, 14, 0, 0),
            notify_callback=fake_notify,
        )
        self.assertEqual(len(res_due), 1)
        self.assertEqual(res_due[0]["reminder"].reminder_type, "due_day")

        # 14:05 -> NÃO repete
        res_due_dup = self.task_service.reminder_service.check_and_notify_due_reminders(
            user_id=self.user.id,
            now=datetime.datetime(2026, 11, 26, 14, 5, 0),
            notify_callback=fake_notify,
        )
        self.assertEqual(len(res_due_dup), 0)

        # Adiar (snooze) 15 minutos a partir de 14:05 -> deve disparar às 14:20
        ok_snooze, _ = self.task_service.reminder_service.snooze_task_reminder(
            task_a.id, minutes=15, now=datetime.datetime(2026, 11, 26, 14, 5, 0)
        )
        self.assertTrue(ok_snooze)
        res_before_snooze = self.task_service.reminder_service.check_and_notify_due_reminders(
            user_id=self.user.id,
            now=datetime.datetime(2026, 11, 26, 14, 15, 0),
            notify_callback=fake_notify,
        )
        self.assertEqual(len(res_before_snooze), 0)
        res_after_snooze = self.task_service.reminder_service.check_and_notify_due_reminders(
            user_id=self.user.id,
            now=datetime.datetime(2026, 11, 26, 14, 21, 0),
            notify_callback=fake_notify,
        )
        self.assertEqual(len(res_after_snooze), 1)

        # Tarefa B: Lembrete de tarefa atrasada (dispara no máx. 1x por dia)
        task_b, _ = self.task_service.create_task(
            self.user.id,
            title="Pagar guia vencida",
            due_date="2026-11-24",
            priority="urgente",
            reminder_enabled=True,
            reminders=[{"reminder_type": "overdue", "remind_time": "09:00", "is_active": True}],
        )
        res_ov1 = self.task_service.reminder_service.check_and_notify_due_reminders(
            user_id=self.user.id,
            now=datetime.datetime(2026, 11, 26, 9, 10, 0),
            notify_callback=fake_notify,
        )
        self.assertEqual(len(res_ov1), 1)
        self.assertEqual(res_ov1[0]["task"].id, task_b.id)
        self.assertEqual(res_ov1[0]["reminder"].reminder_type, "overdue")

        # Mesmo dia às 15:00 -> NÃO repete
        res_ov_same_day = self.task_service.reminder_service.check_and_notify_due_reminders(
            user_id=self.user.id,
            now=datetime.datetime(2026, 11, 26, 15, 0, 0),
            notify_callback=fake_notify,
        )
        self.assertEqual(len(res_ov_same_day), 0)

        # Dia seguinte às 09:05 -> lembra novamente enquanto ainda estiver aberta e atrasada
        res_ov_next_day = self.task_service.reminder_service.check_and_notify_due_reminders(
            user_id=self.user.id,
            now=datetime.datetime(2026, 11, 27, 9, 5, 0),
            notify_callback=fake_notify,
        )
        self.assertEqual(len(res_ov_next_day), 1)

        # Protocolo Toast vinculando diretamente à tarefa
        parsed_open = parse_toast_protocol_url(f"dailynotes://task/open?id={task_a.id}")
        self.assertEqual(parsed_open["action"], "open_task")
        self.assertEqual(parsed_open["task_id"], task_a.id)

        parsed_snooze = parse_toast_protocol_url(f"dailynotes://task/snooze?id={task_a.id}&minutes=15")
        self.assertEqual(parsed_snooze["action"], "snooze_task")
        self.assertEqual(parsed_snooze["task_id"], task_a.id)
        self.assertEqual(parsed_snooze["minutes"], 15)

    # ------------------------------------------------------------------
    # Critério 10 e 11: Persistência, Migração Segura de schedules legados e UI/Diário
    # ------------------------------------------------------------------
    def test_10_and_11_persistence_legacy_migration_and_ui_compatibility(self):
        # 1. Insere um agendamento legado diretamente via ScheduleService (compatibilidade)
        sched_svc = ScheduleService(db_path=self.db_path)
        legacy_sched, msg = sched_svc.create_schedule(
            user_id=self.user.id,
            title="Agendamento Antigo Preservado",
            content="Descrição vinda da versão anterior",
            schedule_date="2026-11-28",
            schedule_time="10:30",
            priority="normal",
            repeat_interval="weekly",
        )
        self.assertIsNotNone(legacy_sched, msg)

        # Executa init_db duas vezes para provar idempotência da migração
        init_db(self.db_path)
        init_db(self.db_path)

        # Nova instância de TaskService (simula fechar e abrir o aplicativo)
        reopened_service = TaskService(db_path=self.db_path)
        migrated = reopened_service.get_task_by_legacy_schedule_id(legacy_sched.id, self.user.id)
        self.assertIsNotNone(migrated)
        self.assertEqual(migrated.title, "Agendamento Antigo Preservado")
        self.assertEqual(migrated.priority, "media")  # 'normal' mapeado para 'media'
        self.assertEqual(migrated.due_date, "2026-11-28")
        self.assertEqual(migrated.due_time, "10:30")
        self.assertEqual(len(migrated.history), 1)
        self.assertEqual(len(migrated.reminders), 1)
        self.assertEqual(migrated.reminders[0].repeat_interval, "weekly")

        # Verifica que não duplicou na segunda chamada de init_db
        all_tasks = reopened_service.list_tasks(self.user.id)
        self.assertEqual(len(all_tasks), 1)

        # Cria uma nota no Diário para validar compatibilidade integrada
        diary_svc = DiaryService(db_path=self.db_path)
        diary_svc.save_entry(self.user.id, "2026-11-28", "Anotação do diário vinculada ao prazo.")

        # Abre a interface real (MainWindow -> SchedulesView -> ações -> fechar e reabrir)
        app = MainWindow(db_path=self.db_path)
        try:
            app.update()
            app._on_login_success(self.user)
            app.update()

            app.navigate_to("schedules")
            app.update()
            sched_view = app.active_view
            self.assertIsNotNone(sched_view)
            self.assertEqual(sched_view.selected_task_id, migrated.id)

            # Registra andamento pela interface
            sched_view.txt_new_update.insert("1.0", "Atualização gravada pela interface gráfica.")
            sched_view._handle_add_progress_update(migrated.id)
            app.update()

            # Altera status pela listagem
            sched_view._handle_inline_status_change(migrated.id, "Em andamento")
            app.update()

            # Testa alternância de tema claro/escuro sem erros
            ctk.set_appearance_mode("light")
            app.update()
            ctk.set_appearance_mode("dark")
            app.update()

            # Abre o diário a partir da data da tarefa
            app._open_diary_from_search("2026-11-28", self.user.id)
            app.update()
            self.assertIn("Anotação do diário", app.active_view.txt_content.get("1.0", "end-1c"))
        finally:
            app.destroy()

        # Reabre serviço (persistência pós-fechamento)
        after_close_svc = TaskService(db_path=self.db_path)
        persisted = after_close_svc.get_task_by_id(migrated.id, self.user.id)
        self.assertEqual(persisted.status, "em_andamento")
        self.assertTrue(
            any("Atualização gravada pela interface gráfica." in h.note for h in persisted.history)
        )

    # ------------------------------------------------------------------
    # Critério 12: Compatibilidade total com Backup e Restauração do SQLite
    # ------------------------------------------------------------------
    def test_12_backup_and_restore_preserves_tasks_history_and_reminders(self):
        backup_svc = BackupService(db_path=self.db_path)

        task, _ = self.task_service.create_task(
            self.user.id,
            title="Tarefa Crítica de Backup",
            description="Deve sobreviver intacta ao ciclo backup/restore.",
            due_date="2026-12-05",
            due_time="15:00",
            priority="urgente",
            category="Infra",
            reminder_enabled=True,
            reminders=[
                {"reminder_type": "due_day", "remind_time": "09:00", "is_active": True},
                {"reminder_type": "overdue", "remind_time": "09:30", "is_active": True},
            ],
        )
        self.task_service.add_progress_update(task.id, self.user.id, "Etapa 1 concluída antes do backup.")
        self.task_service.add_progress_update(task.id, self.user.id, "Etapa 2 validada antes do backup.")

        # Gera backup completo
        bkp_file = os.path.join(self.temp_dir.name, "backup_diario_tasks.db")
        ok_bkp, msg_bkp = backup_svc.create_database_backup(bkp_file)
        self.assertTrue(ok_bkp, msg_bkp)
        self.assertTrue(os.path.isfile(bkp_file))

        # Exclui a tarefa no banco atual (simula perda de dados)
        ok_del, _ = self.task_service.delete_task(task.id, self.user.id)
        self.assertTrue(ok_del)
        self.assertIsNone(self.task_service.get_task_by_id(task.id, self.user.id))

        # Restaura o backup
        ok_res, msg_res = backup_svc.restore_database_backup(bkp_file)
        self.assertTrue(ok_res, msg_res)

        # Valida integridade completa das 3 tabelas após restauração
        restored = self.task_service.get_task_by_id(task.id, self.user.id, include_details=True)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.title, "Tarefa Crítica de Backup")
        self.assertEqual(restored.category, "Infra")
        self.assertEqual(len(restored.history), 3)
        self.assertEqual(restored.history[1].note, "Etapa 1 concluída antes do backup.")
        self.assertEqual(restored.history[2].note, "Etapa 2 validada antes do backup.")
        self.assertEqual(len(restored.reminders), 2)

        # Verifica chaves estrangeiras íntegras no SQLite
        conn = get_connection(self.db_path)
        try:
            fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
            self.assertEqual(fk_errors, [])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
