import unittest
import tempfile
import os
import datetime
from database.migrations import init_db
from models.user import User
from services.authentication_service import AuthenticationService
from services.schedule_service import ScheduleService


class TestScheduleService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_sched.db")
        init_db(self.db_path)
        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.user, _ = self.auth_service.create_initial_admin("admin", "Admin User", "senha1234")
        self.schedule_service = ScheduleService(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_and_get_schedule(self):
        sched, msg = self.schedule_service.create_schedule(
            user_id=self.user.id,
            title="Reunião com Diretoria",
            content="Apresentar o balanço trimestral",
            schedule_date="2026-12-15",
            schedule_time="14:30",
            priority="alta",
            repeat_interval="none",
        )
        self.assertIsNotNone(sched)
        self.assertEqual(sched.title, "Reunião com Diretoria")
        self.assertEqual(sched.schedule_date, "2026-12-15")
        self.assertEqual(sched.schedule_time, "14:30")
        self.assertEqual(sched.priority, "alta")
        self.assertEqual(sched.status, "pendente")
        self.assertEqual(sched.date_br, "15/12/2026")

        fetched = self.schedule_service.get_schedule_by_id(sched.id, self.user.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, "Reunião com Diretoria")
        self.assertEqual(fetched.content, "Apresentar o balanço trimestral")

    def test_update_and_status(self):
        sched, _ = self.schedule_service.create_schedule(
            user_id=self.user.id,
            title="Entrega de Relatório",
            content="Versão inicial",
            schedule_date="2026-12-20",
            schedule_time="10:00",
        )
        self.assertIsNotNone(sched)

        ok, msg = self.schedule_service.update_schedule(
            schedule_id=sched.id,
            user_id=self.user.id,
            title="Entrega de Relatório Final",
            content="Versão final revisada",
            schedule_date="2026-12-21",
            schedule_time="11:30",
            priority="urgente",
        )
        self.assertTrue(ok)

        updated = self.schedule_service.get_schedule_by_id(sched.id, self.user.id)
        self.assertEqual(updated.title, "Entrega de Relatório Final")
        self.assertEqual(updated.schedule_date, "2026-12-21")
        self.assertEqual(updated.schedule_time, "11:30")
        self.assertEqual(updated.priority, "urgente")

        # Concluir agendamento
        ok_comp, _ = self.schedule_service.set_status(sched.id, self.user.id, "concluido")
        self.assertTrue(ok_comp)
        updated2 = self.schedule_service.get_schedule_by_id(sched.id, self.user.id)
        self.assertEqual(updated2.status, "concluido")

    def test_list_and_filters(self):
        today_iso = datetime.date.today().strftime("%Y-%m-%d")
        tomorrow_iso = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_iso = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        # 1. Agendamento para hoje
        self.schedule_service.create_schedule(
            user_id=self.user.id,
            title="Tarefa de Hoje",
            schedule_date=today_iso,
            schedule_time="23:59",
        )
        # 2. Agendamento atrasado (ontem)
        self.schedule_service.create_schedule(
            user_id=self.user.id,
            title="Tarefa Atrasada",
            schedule_date=yesterday_iso,
            schedule_time="08:00",
        )
        # 3. Agendamento para amanhã
        self.schedule_service.create_schedule(
            user_id=self.user.id,
            title="Tarefa de Amanhã",
            schedule_date=tomorrow_iso,
            schedule_time="10:00",
        )

        all_items = self.schedule_service.list_schedules(user_id=self.user.id, filter_status="todos")
        self.assertEqual(len(all_items), 3)

        today_items = self.schedule_service.list_schedules(user_id=self.user.id, filter_status="hoje")
        self.assertEqual(len(today_items), 1)
        self.assertEqual(today_items[0].title, "Tarefa de Hoje")

        overdue_items = self.schedule_service.list_schedules(user_id=self.user.id, filter_status="atrasados")
        self.assertEqual(len(overdue_items), 1)
        self.assertEqual(overdue_items[0].title, "Tarefa Atrasada")

        # Busca textual
        searched = self.schedule_service.list_schedules(user_id=self.user.id, search_query="amanha")
        self.assertEqual(len(searched), 1)
        self.assertEqual(searched[0].title, "Tarefa de Amanhã")

    def test_delete_schedule(self):
        sched, _ = self.schedule_service.create_schedule(
            user_id=self.user.id,
            title="Para Deletar",
            schedule_date="2026-12-01",
        )
        self.assertIsNotNone(sched)

        ok, _ = self.schedule_service.delete_schedule(sched.id, self.user.id)
        self.assertTrue(ok)
        self.assertIsNone(self.schedule_service.get_schedule_by_id(sched.id, self.user.id))

    def test_check_and_notify_due_schedules(self):
        yesterday_iso = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        sched, _ = self.schedule_service.create_schedule(
            user_id=self.user.id,
            title="Lembrete Vencido",
            content="Conteúdo do lembrete vencido",
            schedule_date=yesterday_iso,
            schedule_time="08:00",
        )
        self.assertIsNotNone(sched)
        self.assertEqual(sched.status, "pendente")

        # Dispara verificação
        notified = self.schedule_service.check_and_notify_due_schedules(user_id=self.user.id)
        self.assertEqual(len(notified), 1)
        self.assertEqual(notified[0].id, sched.id)

        # O status deve ter mudado para 'notificado'
        refreshed = self.schedule_service.get_schedule_by_id(sched.id, self.user.id)
        self.assertEqual(refreshed.status, "notificado")
        self.assertIsNotNone(refreshed.notified_at)

        # Próxima checagem não deve notificar novamente
        notified_again = self.schedule_service.check_and_notify_due_schedules(user_id=self.user.id)
        self.assertEqual(len(notified_again), 0)


if __name__ == "__main__":
    unittest.main()

